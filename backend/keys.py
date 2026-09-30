from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from config import TMC_NEURONS, USER_AGENT

WALLETS_DIR = Path(os.getenv("BITTENSOR_WALLET_PATH", os.path.expanduser("~/.bittensor/wallets")))
NEURON_CACHE_SECONDS = 30.0

_lock = threading.Lock()
_registered_cache: tuple[float, set[str]] | None = None


def list_wallets() -> list[str]:
    if not WALLETS_DIR.is_dir():
        return []
    return sorted(path.name for path in WALLETS_DIR.iterdir() if path.is_dir())


def _hotkey_files(wallet: str) -> list[Path]:
    folder = WALLETS_DIR / wallet / "hotkeys"
    if not folder.is_dir():
        return []
    files = [
        path
        for path in folder.iterdir()
        if path.is_file() and not path.name.endswith("pub.txt") and not path.name.startswith(".")
    ]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files


def _hotkey_ss58(wallet: str, name: str) -> str | None:
    pub = WALLETS_DIR / wallet / "hotkeys" / f"{name}pub.txt"
    if not pub.is_file():
        return None
    try:
        data = json.loads(pub.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(data, dict):
        return None
    ss58 = data.get("ss58Address")
    return ss58 if isinstance(ss58, str) and ss58 else None


def _fetch_registered_ss58() -> set[str] | None:
    request = urllib.request.Request(
        TMC_NEURONS,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list):
        return None
    found: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        hotkey = item.get("hotkey")
        if isinstance(hotkey, str) and hotkey:
            found.add(hotkey)
    return found


def registered_ss58(refresh: bool = False) -> set[str] | None:
    global _registered_cache
    now = time.monotonic()
    with _lock:
        if not refresh and _registered_cache and now - _registered_cache[0] < NEURON_CACHE_SECONDS:
            return _registered_cache[1]
    found = _fetch_registered_ss58()
    if found is None:
        with _lock:
            return _registered_cache[1] if _registered_cache else None
    with _lock:
        _registered_cache = (time.monotonic(), found)
    return found


def list_hotkeys(wallet: str, unregistered_only: bool = True, refresh: bool = False) -> list[str]:
    names = [path.name for path in _hotkey_files(wallet)]
    if not unregistered_only:
        return names
    registered = registered_ss58(refresh=refresh)
    if registered is None:
        return names
    available: list[str] = []
    for name in names:
        ss58 = _hotkey_ss58(wallet, name)
        if ss58 and ss58 in registered:
            continue
        available.append(name)
    return available
