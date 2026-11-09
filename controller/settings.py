import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    simulator_url: str
    db_path: str
    advance_minutes: int
    request_timeout_seconds: int


def load_settings() -> Settings:
    return Settings(
        simulator_url=os.environ.get(
            "SIMULATOR_URL",
            "http://127.0.0.1:8700",
        ),
        db_path=os.environ.get("CONTROLLER_DB", "controller.db"),
        advance_minutes=int(os.environ.get("ADVANCE_MINUTES", "15")),
        request_timeout_seconds=int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30")),
    )