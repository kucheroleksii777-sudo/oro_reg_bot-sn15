from __future__ import annotations

import os
import subprocess
from pathlib import Path

from config import ORO_BIN


def _redact(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, "***")


def connect_openrouter(wallet: str, hotkey: str, api_key: str) -> dict:
    key = (api_key or "").strip()
    if not key:
        return {"ok": False, "message": "OpenRouter key is empty."}
    oro = Path(ORO_BIN)
    if not oro.is_file():
        return {"ok": False, "message": "oro CLI not found; OpenRouter was not connected."}
    try:
        proc = subprocess.run(
            [
                str(oro),
                "inference",
                "connect",
                "openrouter",
                "--api-key",
                key,
                "--wallet-name",
                wallet,
                "--wallet-hotkey",
                hotkey,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=os.environ.copy(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "message": f"OpenRouter connect failed: {exc}."}
    if proc.returncode == 0:
        return {"ok": True, "message": "OpenRouter connected."}
    detail = _redact((proc.stderr or proc.stdout or "connect failed").strip(), key)
    return {"ok": False, "message": f"OpenRouter connect failed: {detail[:240]}"}
