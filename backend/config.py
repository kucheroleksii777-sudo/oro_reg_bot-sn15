import os
from pathlib import Path

NETUID = int(os.getenv("NETUID", "15"))
NETWORK = os.getenv("SUBTENSOR_NETWORK", "finney")
DEFAULT_WALLET = os.getenv("WALLET_NAME", "PoWallet")
DEFAULT_HOTKEY = os.getenv("WALLET_HOTKEY", "hotkey1")
POLL_SECONDS = float(os.getenv("REG_POLL_SECONDS", "3"))
RAO_PER_TAO = 1_000_000_000
BLOCK_SECONDS = 12.0
DAY_MS = 24 * 60 * 60 * 1000
MAX_SERIES = 480
ORO_BIN = os.getenv("ORO_BIN", "/root/PoWork/oro/.venv/bin/oro")
OPENROUTER_DELAY_SECONDS = float(os.getenv("OPENROUTER_DELAY_SECONDS", "300"))
TMC_SUBNET = f"https://api.taomarketcap.com/internal/v1/subnets/{NETUID}/"
TMC_BURN = f"https://api.taomarketcap.com/internal/v1/subnets/burn/{NETUID}/"
TMC_NEURONS = f"https://api.taomarketcap.com/internal/v1/subnets/neurons/{NETUID}/"
SECRET_DIR = Path(os.getenv("REG_BOT_SECRET_DIR", os.path.expanduser("~/.reg_bot")))
PASSWORD_FILE = SECRET_DIR / "coldkey_password"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
