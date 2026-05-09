from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _optional_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    path = Path(value)
    if not path.exists():
        return None
    return path


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for FoodBridge GCP/Firebase split architecture."""

    firebase_project_id: str
    firebase_admin_credentials: Path | None
    firebase_database_url: str
    firebase_storage_bucket: str
    firestore_sync_enabled: bool

    google_cloud_project: str
    google_application_credentials: Path | None
    gcp_region: str
    gcp_location: str
    telegram_bot_token: str | None = None
    telegram_master_bot_username: str = "food_bridgebot"
    telegram_slave_webhook_base_url: str | None = None
    telegram_master_secret: str | None = None
    kms_keyring: str = "foodbridge-keyring"
    kms_key_name: str = "telegram-bot-tokens"
    kms_location: str = "asia-south1"
    timer_acceleration: float = 10.0
    frontend_base_url: str = "http://localhost:3000"
    report_verify_secret: str | None = None
    report_verify_base_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    _load_env_file(ROOT_DIR / ".env.local")
    _load_env_file(ROOT_DIR / ".env" / "local")

    firebase_creds = _optional_path("FIREBASE_ADMIN_CREDENTIALS")
    gcp_creds = _optional_path("GOOGLE_APPLICATION_CREDENTIALS")

    return Settings(
        firebase_project_id=_required_env("FIREBASE_PROJECT_ID"),
        firebase_admin_credentials=firebase_creds,
        firebase_database_url=_required_env("FIREBASE_DATABASE_URL"),
        firebase_storage_bucket=_required_env("FIREBASE_STORAGE_BUCKET"),
        firestore_sync_enabled=os.environ.get("FIRESTORE_SYNC_ENABLED", "true").lower() == "true",
        google_cloud_project=_required_env("GOOGLE_CLOUD_PROJECT"),
        google_application_credentials=gcp_creds,
        gcp_region=os.environ.get("GCP_REGION", "asia-south1"),
        gcp_location=os.environ.get("GCP_LOCATION", "asia-south1"),
        telegram_bot_token=os.environ.get("TELEGRAM_MASTER_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or None,
        telegram_master_bot_username=os.environ.get("TELEGRAM_MASTER_BOT_USERNAME", "food_bridgebot"),
        telegram_slave_webhook_base_url=os.environ.get("TELEGRAM_SLAVE_WEBHOOK_BASE_URL") or None,
        telegram_master_secret=os.environ.get("TELEGRAM_MASTER_SECRET") or None,
        kms_keyring=os.environ.get("KMS_KEYRING", "foodbridge-keyring"),
        kms_key_name=os.environ.get("KMS_KEY_NAME", "telegram-bot-tokens"),
        kms_location=os.environ.get("KMS_LOCATION", "asia-south1"),
        timer_acceleration=float(os.environ.get("TIMER_ACCELERATION", "10")),
        frontend_base_url=os.environ.get("FRONTEND_BASE_URL", "http://localhost:3000"),
        report_verify_secret=os.environ.get("REPORT_VERIFY_SECRET") or os.environ.get("TELEGRAM_MASTER_SECRET") or None,
        report_verify_base_url=os.environ.get("REPORT_VERIFY_BASE_URL") or None,
    )
