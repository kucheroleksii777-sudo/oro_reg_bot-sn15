from __future__ import annotations

import asyncio
import json
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from config import DEFAULT_WALLET
from keys import list_hotkeys, list_wallets
from register import WalletUnlockError, verify_coldkey_password
from store import poll_loop, store


class ThresholdBody(BaseModel):
    tao: float = Field(..., ge=0)


class ArmBody(BaseModel):
    wallet: str = ""
    hotkey: str = ""
    password: str | None = None
    openrouter_key: str | None = None
    dry_run: bool = False


@asynccontextmanager
async def lifespan(_app: FastAPI):
    thread = threading.Thread(target=poll_loop, name="reg-fee-poll", daemon=True)
    thread.start()
    yield


app = FastAPI(title="SN15 register bot", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root(request: Request) -> RedirectResponse:
    host = (request.headers.get("host") or "127.0.0.1").split(":")[0]
    return RedirectResponse(url=f"http://{host}:5174/")


@app.get("/api/state")
def get_state(since: int | None = None) -> dict:
    return store.snapshot(since)


@app.get("/api/wallets")
def get_wallets() -> dict:
    return {"wallets": list_wallets()}


@app.get("/api/hotkeys")
def get_hotkeys(wallet: str = "", refresh: bool = False) -> dict:
    name = wallet.strip() or DEFAULT_WALLET
    return {"wallet": name, "hotkeys": list_hotkeys(name, refresh=refresh)}


@app.post("/api/threshold")
def set_threshold(body: ThresholdBody) -> dict:
    store.set_threshold(body.tao)
    return store.snapshot()


@app.post("/api/bot/start")
def start_bot(body: ArmBody) -> dict:
    if store.snapshot()["threshold_tao"] is None:
        raise HTTPException(400, "Set a standard fee line first")
    password = (body.password or "").strip() or store.password
    if not body.dry_run:
        if not password:
            raise HTTPException(400, "Coldkey password is required")
        try:
            verify_coldkey_password(body.wallet or DEFAULT_WALLET, password)
        except WalletUnlockError as exc:
            from eventlog import record

            record(
                "start_rejected",
                wallet=body.wallet,
                hotkey=body.hotkey,
                reason=str(exc),
            )
            raise HTTPException(400, str(exc)) from exc
        store.persist_password(password)
    store.arm(body.wallet, body.hotkey, password, body.dry_run, body.openrouter_key)
    return store.snapshot()


@app.post("/api/bot/stop")
def stop_bot() -> dict:
    store.disarm()
    return store.snapshot()


@app.get("/api/events")
async def events() -> StreamingResponse:
    async def gen():
        first = True
        while True:
            snap = store.snapshot(include_series=first)
            first = False
            yield f"data: {json.dumps(snap)}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
