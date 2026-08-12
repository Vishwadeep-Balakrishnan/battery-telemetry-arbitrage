"""Settings read from environment variables (see .env.example)."""

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


@dataclass
class Settings:
    database_url: str = "postgresql+psycopg://battery:battery@localhost:5432/battery"
    mqtt_enabled: bool = True
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic: str = "battery/telemetry"
    cors_origins: list[str] = field(default_factory=lambda: ["*"])

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", cls.database_url),
            mqtt_enabled=_env_bool("MQTT_ENABLED", True),
            mqtt_host=os.environ.get("MQTT_HOST", cls.mqtt_host),
            mqtt_port=int(os.environ.get("MQTT_PORT", cls.mqtt_port)),
            mqtt_topic=os.environ.get("MQTT_TOPIC", cls.mqtt_topic),
            cors_origins=_env_list("CORS_ORIGINS", "*"),
        )
