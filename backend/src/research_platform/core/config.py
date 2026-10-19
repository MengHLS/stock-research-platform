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
    # Research-source transport is encrypted by default: "verify" checks the
    # certificate chain and the hostname, "verify_ca" pins the issuing CA without
    # hostname matching (MySQL VERIFY_CA semantics), and "disabled" is an explicit
    # plaintext exception for isolated local use. There is deliberately no
    # "prefer"-style mode that silently drops verification after a failure.
    tls: Literal["verify", "verify_ca", "disabled"] = "verify"
    ca_file: Path | None = None
    connect_timeout: int = Field(default=10, ge=1, le=60)
    read_timeout: int = Field(default=60, ge=1, le=600)

    @model_validator(mode="after")
    def validate_tls(self) -> Self:
        if self.tls == "disabled" and self.ca_file:
            raise ValueError("CA file requires verified TLS")
        if self.ca_file:
            if not self.ca_file.is_file():
                raise ValueError("Configured CA file does not exist")
            try:
                ssl.create_default_context(cafile=str(self.ca_file))
            except (ssl.SSLError, OSError) as error:
                # Startup builds the source engine unconditionally, so an unusable
                # bundle would abort create_app() with a bare SSLError instead of
                # reporting a configuration problem.
                raise ValueError("Configured CA file is not a readable PEM bundle") from error
        if self.tls == "verify_ca" and not self.ca_file:
            raise ValueError("TLS=verify_ca requires a pinned CA file")
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
        if self.tls == "disabled":
            options["ssl_disabled"] = True
            return options
        context = ssl.create_default_context(cafile=self.ca_file)
        context.verify_mode = ssl.CERT_REQUIRED
        if self.tls == "verify_ca":
            # Match PyMySQL's workaround for auto-generated MySQL certificates.
            # Only this explicit compatibility mode relaxes RFC 5280 strictness;
            # default verify retains the interpreter's certificate checks.
            context.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
            # MySQL 8 auto-generates its server certificate without any
            # subjectAltName, so hostname matching can never pass against it.
            # Pinned-CA verification still authenticates the peer and keeps the
            # channel encrypted; this mirrors MySQL's own VERIFY_CA and, unlike a
            # "prefer" mode, never falls back to an unverified connection.
            context.check_hostname = False
        options["ssl"] = context
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


class ReviewConfig(BaseModel):
    """Bounds for read-only historical market-review queries."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    cache_seconds: int = Field(default=60, ge=0, le=3600)
    max_window: int = Field(default=120, ge=1, le=120)
    max_range_days: int = Field(default=366, ge=1, le=366)
    # Natural-day lookback used to find a board-history gap or reach the limit.
    lookback_days: int = Field(default=400, ge=121, le=3650)


class TushareConfig(BaseModel):
    """Tushare token stays a secret: never logged, never returned to a client."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    token: SecretStr = Field(min_length=8)
    url: str = Field(default="https://api.tushare.pro", min_length=1, max_length=200)


class ObjectStorageConfig(BaseModel):
    """S3-compatible artifact storage (MinIO in development).

    Ported from the legacy project, which stored run artifacts there and refused
    to pretend a run succeeded when the store was unreachable. The bucket must
    already exist: creating it is a deployment step, not an API side effect.
    """

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    endpoint: str = Field(min_length=1, max_length=200)
    port: int = Field(default=9000, ge=1, le=65535)
    use_ssl: bool = False
    bucket: str = Field(default="research", min_length=1, max_length=63)
    access_key: SecretStr = Field(min_length=1)
    secret_key: SecretStr = Field(min_length=1)
    region: str = Field(default="us-east-1", min_length=1, max_length=64)

    def endpoint_url(self) -> str:
        scheme = "https" if self.use_ssl else "http"
        return f"{scheme}://{self.endpoint}:{self.port}"


class AuthConfig(BaseModel):
    """Session and password policy for the built-in registration/login.

    ``secret`` signs session tokens; it must be long and random. The remaining
    fields bound abuse (lockout) and token lifetime instead of trusting defaults
    scattered across call sites.
    """

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    secret: SecretStr = Field(min_length=32)
    session_ttl_hours: int = Field(default=168, ge=1, le=24 * 30)
    session_cookie: str = Field(default="rp_session", min_length=1, max_length=64)
    cookie_secure: bool = True
    max_failed_logins: int = Field(default=5, ge=1, le=100)
    lockout_minutes: int = Field(default=15, ge=1, le=24 * 60)
    min_password_length: int = Field(default=10, ge=8, le=128)
    # Three registration modes, from most to least open:
    #   open   — anyone may register (only for a trusted, private deployment);
    #   invite — a valid invitation code is required (the default: one or two
    #            users, each account approved in person);
    #   closed — no self-registration at all; accounts are created from the CLI.
    registration: Literal["open", "invite", "closed"] = "invite"
    invitation_ttl_hours: int = Field(default=24 * 14, ge=1, le=24 * 365)


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
    review: ReviewConfig = ReviewConfig()
    tushare: TushareConfig | None = None
    object_storage: ObjectStorageConfig | None = None
    auth: AuthConfig | None = None

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
        """Fail fast on a production start that is not actually ready.

        Authentication now exists, so the previous blanket block is replaced by
        concrete prerequisites: without a signing secret there is no way to issue
        a session, and a production deployment that cannot authenticate would
        serve a login page it can never satisfy. TLS-only cookies are enforced in
        production so a session token is never sent over plain HTTP.
        """
        if self.environment != "production":
            return
        if self.auth is None:
            raise RuntimeError(
                "Production is blocked: configure RP_AUTH__SECRET to enable authentication."
            )
        if not self.auth.cookie_secure:
            raise RuntimeError("Production requires RP_AUTH__COOKIE_SECURE=true")
