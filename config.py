from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return float(raw.replace(",", "."))


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(slots=True)
class Settings:
    bot_token: str
    cryptobot_token: str
    admin_ids: set[int]
    log_chat_id: int | None
    required_channel: str | None
    database_path: str
    cryptobot_asset: str
    cryptobot_base_url: str
    room_min_bet: float
    house_fee_percent: float
    referral_percent: float
    min_deposit: float
    min_withdraw: float
    invoice_poll_interval: int


def load_settings() -> Settings:
    _load_dotenv_file(Path(".env"))

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")

    admin_ids: set[int] = set()
    for part in os.getenv("ADMIN_IDS", "").split(","):
        value = part.strip()
        if value:
            admin_ids.add(int(value))

    log_chat_id_raw = os.getenv("LOG_CHAT_ID", "").strip()
    required_channel = os.getenv("REQUIRED_CHANNEL", "").strip() or None

    return Settings(
        bot_token=bot_token,
        cryptobot_token=os.getenv("CRYPTOBOT_TOKEN", "").strip(),
        admin_ids=admin_ids,
        log_chat_id=int(log_chat_id_raw) if log_chat_id_raw else None,
        required_channel=required_channel,
        database_path=os.getenv("DATABASE_PATH", "bot.sqlite3").strip(),
        cryptobot_asset=os.getenv("CRYPTOBOT_ASSET", "USDT").strip().upper(),
        cryptobot_base_url=os.getenv("CRYPTOBOT_BASE_URL", "https://pay.crypt.bot/api").strip().rstrip("/"),
        room_min_bet=_get_float("ROOM_MIN_BET", 0.05),
        house_fee_percent=_get_float("HOUSE_FEE_PERCENT", 1.0),
        referral_percent=_get_float("REFERRAL_PERCENT", 0.01),
        min_deposit=_get_float("MIN_DEPOSIT", 0.05),
        min_withdraw=_get_float("MIN_WITHDRAW", 0.05),
        invoice_poll_interval=_get_int("INVOICE_POLL_INTERVAL", 20),
    )


def build_default_settings_map(settings: Settings) -> dict[str, str]:
    return {
        "room_min_bet": str(settings.room_min_bet),
        "house_fee_percent": str(settings.house_fee_percent),
        "referral_percent": str(settings.referral_percent),
        "min_deposit": str(settings.min_deposit),
        "min_withdraw": str(settings.min_withdraw),
        "required_channel": settings.required_channel or "",
    }
