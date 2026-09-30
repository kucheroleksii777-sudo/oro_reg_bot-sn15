from __future__ import annotations

import os
import threading
import time
from typing import Any

from config import (
    DAY_MS,
    DEFAULT_HOTKEY,
    DEFAULT_WALLET,
    MAX_SERIES,
    NETUID,
    NETWORK,
    OPENROUTER_DELAY_SECONDS,
    PASSWORD_FILE,
    POLL_SECONDS,
    SECRET_DIR,
)
from eventlog import record
from fee import detect_reg_jumps, fetch_history, fetch_history_since, fetch_snapshot, live_fee, now_iso
from openrouter import connect_openrouter
from register import register_hotkey


def _window(
    points: list[dict],
    now_ms: int,
    max_points: int = MAX_SERIES,
    keep: list[dict] | None = None,
) -> list[dict]:
    cutoff = now_ms - DAY_MS
    kept = [point for point in points if point["t"] >= cutoff]
    have = {point["t"] for point in kept}
    for point in keep or []:
        if point["t"] >= cutoff and point["t"] not in have:
            kept.append(point)
            have.add(point["t"])
    kept.sort(key=lambda point: point["t"])
    if len(kept) <= max_points:
        return kept
    last = kept[-1]
    span = max(1, max_points - 1)
    sampled = [kept[round(i * (len(kept) - 1) / span)] for i in range(max_points)]
    sampled[-1] = last
    return sampled


class Store:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.series: list[dict] = []
        self.regs: list[dict] = []
        self.fee_tao: float | None = None
        self.threshold_tao: float | None = None
        self.last_raw_burn: int | None = None
        self.updated_at: str | None = None
        self.error: str | None = None
        self.armed = False
        self.dry_run = False
        self.wallet = DEFAULT_WALLET
        self.hotkey = DEFAULT_HOTKEY
        self.password: str | None = None
        self.openrouter_key: str | None = None
        self.busy = False
        self.registered = False
        self.last_trigger: dict | None = None
        self.bot_error: str | None = None
        self._last_attempt = 0.0
        self._or_job: dict[str, Any] | None = None
        self._or_status: str | None = None
        self._or_message: str | None = None
        self.password = self._load_password()

    def _load_password(self) -> str | None:
        try:
            raw = PASSWORD_FILE.read_text(encoding="utf-8")
        except OSError:
            return None
        secret = raw.strip()
        return secret or None

    def persist_password(self, password: str | None) -> None:
        secret = (password or "").strip()
        self.password = secret or None
        try:
            SECRET_DIR.mkdir(parents=True, exist_ok=True)
            os.chmod(SECRET_DIR, 0o700)
            if not secret:
                PASSWORD_FILE.unlink(missing_ok=True)
                return
            tmp = PASSWORD_FILE.with_suffix(".tmp")
            tmp.write_text(secret + "\n", encoding="utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(PASSWORD_FILE)
            os.chmod(PASSWORD_FILE, 0o600)
        except OSError:
            pass

    def latest_t(self) -> int | None:
        with self.lock:
            return self.series[-1]["t"] if self.series else None

    def snapshot(self, since: int | None = None, include_series: bool = True) -> dict[str, Any]:
        with self.lock:
            if include_series:
                series = list(self.series)
                regs = list(self.regs)
                if since is not None:
                    series = [point for point in series if point["t"] > since]
                    regs = [point for point in regs if point["t"] > since]
                delta = since is not None
            else:
                series = []
                regs = []
                delta = True
            return {
                "netuid": NETUID,
                "network": NETWORK,
                "fee_tao": self.fee_tao,
                "threshold_tao": self.threshold_tao,
                "series": series,
                "regs": regs,
                "updated_at": self.updated_at,
                "error": self.error,
                "delta": delta,
                "bot": {
                    "armed": self.armed,
                    "dry_run": self.dry_run,
                    "wallet": self.wallet,
                    "hotkey": self.hotkey,
                    "busy": self.busy,
                    "registered": self.registered,
                    "has_password": bool(self.password),
                    "last_trigger": self.last_trigger,
                    "error": self.bot_error,
                    "openrouter": self._openrouter_public(),
                },
            }

    def _openrouter_public(self) -> dict[str, Any]:
        job = self._or_job
        return {
            "status": self._or_status,
            "due_at": int(job["due_at"]) if job and job.get("due_at") else None,
            "wallet": job.get("wallet") if job else None,
            "hotkey": job.get("hotkey") if job else None,
            "message": self._or_message,
        }

    def set_threshold(self, tao: float) -> None:
        with self.lock:
            self.threshold_tao = max(0.0, float(tao))

    def arm(
        self,
        wallet: str,
        hotkey: str,
        password: str | None,
        dry_run: bool,
        openrouter_key: str | None = None,
    ) -> None:
        with self.lock:
            self.wallet = wallet.strip() or DEFAULT_WALLET
            self.hotkey = hotkey.strip() or DEFAULT_HOTKEY
            incoming = (password or "").strip() or None
            if incoming:
                self.persist_password(incoming)
            elif not self.password:
                self.password = self._load_password()
            self.openrouter_key = (openrouter_key or "").strip() or None
            self.dry_run = bool(dry_run)
            self.armed = True
            self.registered = False
            self.bot_error = None
        record(
            "start",
            wallet=self.wallet,
            hotkey=self.hotkey,
            dry_run=self.dry_run,
            threshold_tao=self.threshold_tao,
            has_password=bool(self.password),
        )

    def disarm(self) -> None:
        with self.lock:
            self.armed = False
            self.openrouter_key = None
            self.busy = False
            if not self.password:
                self.password = self._load_password()
        record("stop", wallet=self.wallet, hotkey=self.hotkey)

    def seed_history(self) -> None:
        try:
            points = fetch_history("1D")
        except Exception as exc:
            with self.lock:
                self.error = f"history: {exc}"
            return
        regs, jump_keep = detect_reg_jumps(points)
        now_ms = int(time.time() * 1000)
        regs = _window(regs, now_ms, max_points=400)
        points = _window(points, now_ms, keep=jump_keep)
        with self.lock:
            self.series = points
            self.regs = regs
            if points:
                self.fee_tao = points[-1]["tao"]
            self.updated_at = now_iso()
            self.error = None

    def tick(self) -> None:
        self._maybe_start_openrouter()
        now_ms = int(time.time() * 1000)
        with self.lock:
            last_t = self.series[-1]["t"] if self.series else now_ms - DAY_MS
        try:
            incoming = fetch_history_since(last_t)
            snap = fetch_snapshot()
            fee = live_fee(snap)
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
            return

        live = {"t": now_ms, "tao": fee}
        should_fire = False
        job: dict[str, Any] | None = None

        with self.lock:
            bridge = (self.series[-1:] if self.series else []) + incoming
            events, jump_keep = detect_reg_jumps(bridge)
            have = {point["t"] for point in self.series}
            for point in incoming:
                if point["t"] not in have:
                    self.series.append(point)
                    have.add(point["t"])
                elif point["t"] == self.series[-1]["t"]:
                    self.series[-1] = point
            live_point = {"t": now_ms, "tao": fee, "live": True}
            if self.series and (self.series[-1].get("live") or now_ms - self.series[-1]["t"] < 5000):
                self.series[-1] = live_point
            else:
                self.series.append(live_point)
            self.series.sort(key=lambda point: point["t"])
            seen_reg = {point["t"] for point in self.regs}
            for event in events:
                if event["t"] not in seen_reg:
                    self.regs.append(event)
                    seen_reg.add(event["t"])
            self.last_raw_burn = snap["burn_rao"]
            self.fee_tao = fee
            self.updated_at = now_iso()
            self.error = None
            self.regs = _window(self.regs, now_ms, max_points=400)
            self.series = _window(self.series, now_ms, keep=jump_keep + self.regs)
            if (
                self.armed
                and not self.busy
                and not self.registered
                and self.threshold_tao is not None
                and fee <= self.threshold_tao
                and (time.time() - self._last_attempt) > 20
            ):
                self.busy = True
                self._last_attempt = time.time()
                should_fire = True
                job = {
                    "wallet": self.wallet,
                    "hotkey": self.hotkey,
                    "password": self.password,
                    "openrouter_key": self.openrouter_key,
                    "dry_run": self.dry_run,
                    "fee_tao": fee,
                    "threshold_tao": self.threshold_tao,
                }

        if should_fire and job:
            record(
                "trigger",
                wallet=job["wallet"],
                hotkey=job["hotkey"],
                fee_tao=job["fee_tao"],
                threshold_tao=job["threshold_tao"],
                dry_run=job["dry_run"],
            )
            self._run_register(job)

    def _run_register(self, job: dict[str, Any]) -> None:
        try:
            result = register_hotkey(
                wallet_name=job["wallet"],
                hotkey=job["hotkey"],
                password=job["password"],
                netuid=NETUID,
                network=NETWORK,
                dry_run=job["dry_run"],
            )
            if (
                result.get("ok")
                and not result.get("dry_run")
                and not job["dry_run"]
                and job.get("openrouter_key")
            ):
                wait_min = max(1, int(OPENROUTER_DELAY_SECONDS // 60))
                message = result.get("message") or "Registration submitted."
                result = {
                    **result,
                    "message": f"{message} OpenRouter will connect in {wait_min} minutes.",
                }
            with self.lock:
                self.last_trigger = {
                    "at": now_iso(),
                    "fee_tao": job["fee_tao"],
                    "threshold_tao": job["threshold_tao"],
                    **{k: v for k, v in result.items() if k not in ("password", "openrouter_key")},
                }
                self.bot_error = None if result.get("ok") else result.get("message")
                if result.get("ok"):
                    self.registered = not bool(result.get("dry_run") or job["dry_run"])
                    self.armed = False
                    if not self.password:
                        self.password = self._load_password()
                    if (
                        self.registered
                        and job.get("openrouter_key")
                    ):
                        self._or_job = {
                            "wallet": job["wallet"],
                            "hotkey": job["hotkey"],
                            "key": job["openrouter_key"],
                            "due_at": time.time() + OPENROUTER_DELAY_SECONDS,
                        }
                        self._or_status = "pending"
                        self._or_message = "OpenRouter will connect in 5 minutes."
                    self.openrouter_key = None
            record(
                "register_result",
                wallet=job["wallet"],
                hotkey=job["hotkey"],
                fee_tao=job["fee_tao"],
                threshold_tao=job["threshold_tao"],
                ok=bool(result.get("ok")),
                dry_run=bool(result.get("dry_run") or job["dry_run"]),
                already=bool(result.get("already")),
                message=result.get("message"),
            )
        except Exception as exc:
            with self.lock:
                self.bot_error = str(exc)
                self.last_trigger = {
                    "at": now_iso(),
                    "fee_tao": job["fee_tao"],
                    "ok": False,
                    "message": str(exc),
                }
            record(
                "register_error",
                wallet=job["wallet"],
                hotkey=job["hotkey"],
                fee_tao=job["fee_tao"],
                error=str(exc) or type(exc).__name__,
            )
        finally:
            with self.lock:
                self.busy = False

    def _maybe_start_openrouter(self) -> None:
        job: dict[str, Any] | None = None
        with self.lock:
            pending = self._or_job
            if (
                pending
                and self._or_status == "pending"
                and pending.get("key")
                and time.time() >= float(pending["due_at"])
            ):
                self._or_status = "connecting"
                self._or_message = "Connecting OpenRouter…"
                job = {
                    "wallet": pending["wallet"],
                    "hotkey": pending["hotkey"],
                    "key": pending["key"],
                }
        if job:
            threading.Thread(
                target=self._run_openrouter,
                args=(job,),
                daemon=True,
                name="or-connect",
            ).start()

    def _run_openrouter(self, job: dict[str, Any]) -> None:
        linked = connect_openrouter(job["wallet"], job["hotkey"], job["key"])
        with self.lock:
            self._or_status = "connected" if linked.get("ok") else "error"
            self._or_message = linked.get("message")
            if self._or_job:
                self._or_job["key"] = None
            if self.last_trigger is not None:
                prior = self.last_trigger.get("message") or ""
                self.last_trigger = {
                    **self.last_trigger,
                    "openrouter_ok": linked.get("ok"),
                    "message": f"{prior} {linked.get('message') or ''}".strip(),
                }


store = Store()


def poll_loop() -> None:
    store.seed_history()
    while True:
        store.tick()
        time.sleep(POLL_SECONDS)
