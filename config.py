"""Settings loaded from environment variables (or a .env file)."""

import json
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


TOKEN = _require("TOKEN_API")
GSHEET_KEY_ID = _require("GSHEET_KEY_ID")
GSHEET_CREDENTIALS: dict = json.loads(_require("GSHEET_CREDENTIALS"))

# {"<telegram id>": "<display name>"}
ADMIN_USERS: dict[int, str] = {int(k): v for k, v in json.loads(_require("ADMIN_USERS")).items()}
# [<telegram id>, ...] — admins are always allowed too.
BROADCAST_USERS: set[int] = {int(u) for u in json.loads(_require("ALLOWED_USERS"))}
ALLOWED_USERS: set[int] = BROADCAST_USERS | set(ADMIN_USERS)

WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Booking_Details")
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Singapore"))
BOOKING_WINDOW_DAYS = int(os.getenv("BOOKING_WINDOW_DAYS", "90"))
PERSISTENCE_FILE = os.getenv("PERSISTENCE_FILE", "bot_state.pickle")

FACILITIES = [
    "Multi-Purpose Hall",
    "Basketball Court",
    "Football Field",
    "Swimming Pool",
]
