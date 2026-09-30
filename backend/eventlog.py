from __future__ import annotations

import json
from pathlib import Path

from config import SECRET_DIR
from fee import now_iso

LOG_PATHS = (
    Path("/tmp/reg_bot/register.log"),
    SECRET_DIR / "register.log",
)


def record(event: str, **fields: object) -> None:
    line = json.dumps(
        {"at": now_iso(), "event": event, **fields},
        default=str,
        ensure_ascii=False,
    )
    for path in LOG_PATHS:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            continue
