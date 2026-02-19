import os
from dotenv import load_dotenv

load_dotenv()

MODEL: str | None = os.getenv("MODEL")
DB_URL: str | None = os.getenv("DB_URL")

def _validate_settings():
    missing = []

    if not MODEL:
        missing.append("MODEL")
    if not DB_URL:
        missing.append("DB_URL")

    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

_validate_settings()