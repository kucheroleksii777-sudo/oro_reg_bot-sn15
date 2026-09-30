from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

from config import BLOCK_SECONDS, MAX_SERIES, RAO_PER_TAO, TMC_BURN, TMC_SUBNET, USER_AGENT


def rao_to_tao(rao: int | float) -> float:
    return float(rao) / RAO_PER_TAO


def _get_json(url: str, timeout: float = 12) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="ignore"))


def decay_burn_rao(burn_rao: int, min_burn: int, half_life: float, fetched_at: float) -> int:
    if burn_rao <= 0 or half_life <= 0:
        return burn_rao
    elapsed_blocks = int(max(0.0, time.time() - fetched_at) / BLOCK_SECONDS)
    if elapsed_blocks <= 0:
        return burn_rao
    decayed = burn_rao * (0.5 ** (elapsed_blocks / half_life))
    return max(min_burn, int(decayed))


def fetch_snapshot() -> dict:
    payload = _get_json(TMC_SUBNET)
    snap = payload.get("latest_snapshot")
    if not isinstance(snap, dict):
        raise ValueError("missing TMC snapshot")
    burn_rao = int(snap.get("burn") or 0)
    if burn_rao <= 0:
        raise ValueError("missing TMC burn")
    return {
        "burn_rao": burn_rao,
        "min_burn": int(snap.get("min_burn") or 100_000_000),
        "half_life": float(snap.get("burn_half_life") or 360.0),
        "fetched_at": time.time(),
    }


_history_cache: dict[str, Any] = {"at": 0.0, "points": []}
HISTORY_CACHE_SECONDS = 30.0


def fetch_history(span: str = "1D") -> list[dict]:
    payload = _get_json(f"{TMC_BURN}?span={span}", timeout=70)
    if not isinstance(payload, list):
        return []
    points: list[dict] = []
    for item in payload:
        try:
            burn = item.get("burn")
            raw_ts = item.get("timestamp")
            if burn is None or raw_ts is None:
                continue
            ts = int(datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00")).timestamp() * 1000)
            points.append({"t": ts, "tao": rao_to_tao(int(burn))})
        except (TypeError, ValueError):
            continue
    points.sort(key=lambda point: point["t"])
    if len(points) > MAX_SERIES:
        last = points[-1]
        span = max(1, MAX_SERIES - 1)
        points = [points[round(i * (len(points) - 1) / span)] for i in range(MAX_SERIES)]
        points[-1] = last
    _history_cache["at"] = time.time()
    _history_cache["points"] = points
    return points


def fetch_history_since(since_ms: int) -> list[dict]:
    cached = _history_cache["points"]
    fresh = time.time() - float(_history_cache["at"]) < HISTORY_CACHE_SECONDS
    points = cached if fresh and cached else fetch_history("1D")
    return [point for point in points if point["t"] > since_ms]


def detect_reg_jumps(
    points: list[dict], min_ratio: float = 1.08, min_delta: float = 0.0004
) -> tuple[list[dict], list[dict]]:
    """Dots land on the last point before the fee jump; peaks stay on the line."""
    events: list[dict] = []
    keep: list[dict] = []
    for prev, cur in zip(points, points[1:]):
        if cur["tao"] > prev["tao"] * min_ratio and (cur["tao"] - prev["tao"]) >= min_delta:
            events.append({"t": prev["t"], "tao": prev["tao"]})
            keep.append({"t": prev["t"], "tao": prev["tao"]})
            keep.append({"t": cur["t"], "tao": cur["tao"]})
    return events, keep


def detect_reg_events(points: list[dict], min_ratio: float = 1.08, min_delta: float = 0.0004) -> list[dict]:
    events, _keep = detect_reg_jumps(points, min_ratio, min_delta)
    return events


def live_fee(snapshot: dict) -> float:
    return rao_to_tao(
        decay_burn_rao(
            snapshot["burn_rao"],
            snapshot["min_burn"],
            snapshot["half_life"],
            snapshot["fetched_at"],
        )
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
