import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    source: str = "chirpstack-local"
    mqtt_enabled: bool = False
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_tls: bool = False
    mqtt_client_id: str = "satlink-telemetry"
    port: int = 8000
    allowed_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173",
                                       "http://localhost:8000", "http://127.0.0.1:8000")

    def __post_init__(self) -> None:
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("SATLINK_DATABASE_URL debe usar postgresql+psycopg")
        if not self.source or len(self.source) > 128:
            raise ValueError("Origen ChirpStack inválido")
        if self.mqtt_enabled and not self.mqtt_host:
            raise ValueError("Configura SATLINK_MQTT_HOST antes de habilitar MQTT")
        if not 1 <= self.port <= 65535 or not 1 <= self.mqtt_port <= 65535:
            raise ValueError("Puerto inválido")
        for origin in self.allowed_origins:
            url = urlsplit(origin)
            if (url.scheme not in ("http", "https") or url.hostname not in ("localhost", "127.0.0.1", "::1")
                    or url.path or url.query or url.fragment or url.username or url.password):
                raise ValueError("Solo se permiten orígenes locales explícitos")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        def flag(name: str) -> bool:
            value = os.getenv(name, "false").lower()
            if value not in ("true", "false"):
                raise ValueError(f"{name} debe ser true o false")
            return value == "true"
        url = os.getenv("SATLINK_DATABASE_URL", "")
        origins = os.getenv("SATLINK_ALLOWED_ORIGINS")
        options = {} if origins is None else {"allowed_origins": tuple(o.strip() for o in origins.split(",") if o.strip())}
        return cls(database_url=url, source=os.getenv("SATLINK_CHIRPSTACK_SOURCE", "chirpstack-local"),
                   mqtt_enabled=flag("SATLINK_MQTT_ENABLED"), mqtt_host=os.getenv("SATLINK_MQTT_HOST", ""),
                   mqtt_port=int(os.getenv("SATLINK_MQTT_PORT", "1883")),
                   mqtt_username=os.getenv("SATLINK_MQTT_USERNAME") or None,
                   mqtt_password=os.getenv("SATLINK_MQTT_PASSWORD") or None,
                   mqtt_tls=flag("SATLINK_MQTT_TLS"),
                   mqtt_client_id=os.getenv("SATLINK_MQTT_CLIENT_ID", "satlink-telemetry"),
                   port=int(os.getenv("SATLINK_PORT", "8000")), **options)
