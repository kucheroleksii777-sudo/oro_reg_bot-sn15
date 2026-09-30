from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from eventlog import record


class WalletUnlockError(RuntimeError):
    """Coldkey password missing or rejected. Never fall through to a stdin prompt."""


def _unlock_wallet(wallet: Any, password: str | None) -> None:
    secret = (password or os.getenv("WALLET_PASSWORD") or os.getenv("BT_WALLET_PASSWORD") or "").strip()
    if not secret:
        raise WalletUnlockError(
            "No coldkey password on the server. Type it in the box, then click Start."
        )

    get_coldkey = getattr(wallet, "get_coldkey", None)
    if not callable(get_coldkey):
        raise WalletUnlockError("This bittensor Wallet has no get_coldkey")

    try:
        from bittensor.keyfiles import WrongPasswordError
    except ImportError:
        WrongPasswordError = Exception  # type: ignore[misc,assignment]

    try:
        keypair = get_coldkey(secret)
    except WrongPasswordError as exc:
        raise WalletUnlockError("Coldkey password is wrong.") from exc
    except Exception as exc:
        name = type(exc).__name__
        if "WrongPassword" in name or "password" in str(exc).lower():
            raise WalletUnlockError("Coldkey password is wrong.") from exc
        raise WalletUnlockError(f"Could not unlock coldkey: {exc}") from exc

    if keypair is None:
        raise WalletUnlockError("Coldkey unlock returned nothing.")
    wallet._coldkey = keypair


def verify_coldkey_password(wallet_name: str, password: str | None) -> None:
    """Unlock the coldkey only. Raises WalletUnlockError if the password is bad."""
    try:
        import bittensor as bt
    except ImportError as exc:
        raise WalletUnlockError(
            "bittensor is not installed. From the venv: pip install bittensor bittensor-wallet"
        ) from exc

    name = (wallet_name or "").strip() or "default"
    wallet = bt.Wallet(name=name) if hasattr(bt, "Wallet") else bt.wallet(name=name)
    _unlock_wallet(wallet, password)


def _hotkey_ss58(wallet: Any) -> str | None:
    hotkey = getattr(wallet, "hotkey", None)
    ss58 = getattr(hotkey, "ss58_address", None)
    return ss58 if isinstance(ss58, str) and ss58 else None


def _is_registered(sub: Any, netuid: int, wallet: Any) -> bool:
    ss58 = _hotkey_ss58(wallet)
    if not ss58:
        return False
    reader = getattr(sub, "read", None)
    if callable(reader):
        try:
            uid = reader("uid", hotkey_ss58=ss58, netuid=netuid)
            if uid is not None:
                return True
        except Exception:
            pass
        try:
            netuids = reader("netuids_for_hotkey", hotkey_ss58=ss58) or []
            return int(netuid) in {int(item) for item in netuids}
        except Exception:
            pass
    for name in ("is_hotkey_registered", "is_hotkey_registered_on_subnet"):
        fn = getattr(sub, name, None)
        if not callable(fn):
            continue
        try:
            return bool(fn(netuid=netuid, hotkey_ss58=ss58))
        except TypeError:
            try:
                return bool(fn(ss58, netuid))
            except Exception:
                continue
        except Exception:
            continue
    return False


@contextmanager
def _password_env(password: str) -> Iterator[None]:
    """bittensor execute() re-unlocks via BT_WALLET_PASSWORD, not wallet._coldkey."""
    key = "BT_WALLET_PASSWORD"
    old = os.environ.get(key)
    os.environ[key] = password
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old


def _submit_register(bt: Any, sub: Any, wallet: Any, netuid: int) -> Any:
    if hasattr(sub, "burned_register"):
        return sub.burned_register(
            wallet=wallet,
            netuid=netuid,
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )
    if hasattr(sub, "register"):
        return sub.register(wallet=wallet, netuid=netuid)
    try:
        from bittensor.intents import BurnedRegister
    except ImportError as exc:
        raise RuntimeError("This bittensor build has no burned_register/register method") from exc
    ss58 = _hotkey_ss58(wallet)
    return sub.execute(BurnedRegister(netuid=netuid, hotkey_ss58=ss58), wallet)


def register_hotkey(
    wallet_name: str,
    hotkey: str,
    password: str | None,
    netuid: int,
    network: str,
    dry_run: bool,
) -> dict:
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "message": f"Would register {wallet_name}/{hotkey} on netuid {netuid}.",
        }

    try:
        import bittensor as bt
    except ImportError as exc:
        raise RuntimeError(
            "bittensor is not installed. From the venv: pip install bittensor bittensor-wallet"
        ) from exc

    secret = (password or os.getenv("WALLET_PASSWORD") or os.getenv("BT_WALLET_PASSWORD") or "").strip()
    wallet_kw: dict[str, Any] = {"name": wallet_name, "hotkey": hotkey}
    wallet = bt.Wallet(**wallet_kw) if hasattr(bt, "Wallet") else bt.wallet(**wallet_kw)
    _unlock_wallet(wallet, secret)
    record("unlock_ok", wallet=wallet_name, hotkey=hotkey)

    sub = bt.Subtensor(network=network) if hasattr(bt, "Subtensor") else bt.subtensor(network=network)
    try:
        if _is_registered(sub, netuid, wallet):
            record("already_registered", wallet=wallet_name, hotkey=hotkey)
            return {
                "ok": True,
                "already": True,
                "dry_run": False,
                "message": f"{hotkey} is already registered on netuid {netuid}.",
            }

        record("submit", wallet=wallet_name, hotkey=hotkey, netuid=netuid)
        with _password_env(secret):
            result = _submit_register(bt, sub, wallet, netuid)
        ok = True if result is None else bool(getattr(result, "success", result))
        message = getattr(result, "message", None)
        return {
            "ok": ok,
            "already": False,
            "dry_run": False,
            "message": message
            or ("Registration submitted." if ok else f"Registration returned {result!r}."),
        }
    except WalletUnlockError:
        raise
    except EOFError as exc:
        raise WalletUnlockError(
            "Register asked for the coldkey password again and had no TTY."
        ) from exc
    except Exception as exc:
        text = str(exc).strip() or type(exc).__name__
        raise WalletUnlockError(f"Registration failed: {text}") from exc
    finally:
        closer = getattr(sub, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass
