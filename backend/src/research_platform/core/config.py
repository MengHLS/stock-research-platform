import ssl
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class MySQLConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    host: str = Field(min_length=1)
    port: int = Field(default=3306, ge=1, le=65535)
    database: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)
    tls: Literal["verify", "disabled"] = "verify"
    ca_file: Path | None = None
    connect_timeout: int = Field(default=10, ge=1, le=60)
    read_timeout: int = Field(default=60, ge=1, le=600)

    @model_validator(mode="after")
    def validate_tls(self) -> Self:
        if self.tls == "disabled" and self.ca_file:
            raise ValueError("CA file requires verified TLS")
        if self.ca_file and not self.ca_file.is_file():
            raise ValueError("Configured CA file does not exist")
        return self

    def url(self) -> URL:
        return URL.create(
            "mysql+pymysql",
            host=self.host,
            port=self.port,
            database=self.database,
            username=self.username,
            password=self.password.get_secret_value(),
            query={"charset": "utf8mb4"},
        )

    def connect_args(self) -> dict:
        options = {"connect_timeout": self.connect_timeout, "read_timeout": self.read_timeout}
        if self.tls == "verify":
            options["ssl"] = ssl.create_default_context(cafile=self.ca_file)
        else:
            options["ssl_disabled"] = True
        return options


class UpstreamConfig(BaseModel):
    """Process-wide bounds for public data services (no credentials, no writes)."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    enabled: bool = True
    timeout_seconds: float = Field(default=10.0, ge=1, le=60)
    # The documented contract is "at most one retry"; the field cannot exceed it.
    max_retries: int = Field(default=1, ge=0, le=1)
    min_interval_ms: int = Field(default=200, ge=0, le=5000)
    quote_cache_seconds: int = Field(default=5, ge=0, le=300)
    intraday_cache_seconds: int = Field(default=30, ge=0, le=3600)
    # Optional per-host address override, e.g. {"push2his.eastmoney.com": ["119.3.232.150"]}.
    #
    # Local proxies in fake-ip mode answer DNS with an address from 198.18.0.0/15
    # that the proxy is supposed to intercept. For hosts whose TLS handshake the
    # local stack cannot complete (Eastmoney asks for renegotiation, which
    # Windows schannel refuses), that interception fails and the host looks down
    # even though it is reachable directly. This map lets the operator pin the
    # real address for such a host while TLS still verifies against the hostname;
    # it is empty by default so no address is baked into the code.
    host_addresses: dict[str, list[str]] = Field(default_factory=dict)


class TushareConfig(BaseModel):
    """Tushare token stays a secret: never logged, never returned to a client."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    token: SecretStr = Field(min_length=8)
    url: str = Field(default="https://api.tushare.pro", min_length=1, max_length=200)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RP_",
        env_file=".env",
        extra="ignore",
        env_nested_delimiter="__",
        env_ignore_empty=True,
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = SecretStr("sqlite:///.scratch/development.db")
    database_mysql: MySQLConfig | None = None
    source_mysql: MySQLConfig | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    upstream: UpstreamConfig = UpstreamConfig()
    tushare: TushareConfig | None = None

    @model_validator(mode="after")
    def validate_database_roles(self) -> Self:
        try:
            app_url = make_url(self.application_url())
        except (ArgumentError, ValueError):
            raise ValueError("Invalid application database URL") from None
        if app_url.drivername not in ("sqlite", "mysql+pymysql"):
            raise ValueError("Application driver must be sqlite or mysql+pymysql")
        if self.database_mysql and self.database_url.get_secret_value() != (
            "sqlite:///.scratch/development.db"
        ):
            raise ValueError("Use either RP_DATABASE_URL or RP_DATABASE_MYSQL, not both")
        if self.source_mysql:
            app = app_url
            source = self.source_mysql
            if app.drivername.startswith("mysql") and (
                (app.host or "").lower(),
                app.port or 3306,
                (app.database or "").lower(),
            ) == (source.host.lower(), source.port, source.database.lower()):
                raise ValueError("Application and source databases must be separate")
        return self

    def application_url(self) -> str | URL:
        if self.database_mysql:
            return self.database_mysql.url()
        return self.database_url.get_secret_value()

    def require_development_release(self) -> None:
        if self.environment == "production":
            raise RuntimeError(
                "Production is blocked: implement real authentication, resource authorization "
                "and deployment acceptance before releasing this starter."
            )
