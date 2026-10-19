import datetime
import runpy
import ssl
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pydantic import ValidationError

from research_platform.core.config import MySQLConfig, Settings
from research_platform.core.database import make_application_engine, make_source_engine


def profile(**changes):
    return dict(
        host="source.example.invalid",
        database="market",
        username="reader",
        password="secret@:/#%value",
        **changes,
    )


def write_ca_bundle(path: Path) -> Path:
    """Write a real, parseable CA certificate so the TLS context is not faked."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-ca")])
    moment = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(moment - datetime.timedelta(days=1))
        .not_valid_after(moment + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return path


def test_default_source_is_disabled_and_application_stays_local():
    settings = Settings(_env_file=None)
    assert settings.source_mysql is None
    assert settings.application_url() == "sqlite:///.scratch/development.db"
    with pytest.raises(ValueError, match="SOURCE_NOT_CONFIGURED"):
        make_source_engine(settings)


def test_nested_environment_and_password_round_trip(monkeypatch):
    for key, value in profile().items():
        monkeypatch.setenv(f"RP_SOURCE_MYSQL__{key.upper()}", value)
    monkeypatch.setenv("RP_SOURCE_MYSQL__PORT", "4000")
    settings = Settings(_env_file=None)
    source = settings.source_mysql
    assert source is not None
    assert source.url().password == "secret@:/#%value"
    assert source.url().port == 4000
    assert "secret@:/#%value" not in repr(settings)
    assert "secret@:/#%value" not in str(source.url())


def test_tls_verifies_certificate_and_hostname_by_default():
    config = MySQLConfig(**profile())
    context = config.connect_args()["ssl"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert config.connect_args()["connect_timeout"] == 10
    assert config.connect_args()["read_timeout"] == 60


def test_tls_verify_ca_pins_the_ca_without_hostname_matching(tmp_path):
    """MySQL VERIFY_CA semantics: chain pinned, hostname not matched.

    MySQL 8 auto-generates its server certificate without any subjectAltName, so
    hostname matching can never pass against it. ``verify_ca`` keeps the encrypted
    channel and CA validation and only drops hostname matching; unlike a "prefer"
    mode it never degrades to an unverified connection.

    A real certificate is used here on purpose: asserting against a hand-made
    context would only restate that context's own defaults.
    """
    ca_file = write_ca_bundle(tmp_path / "source-ca.pem")

    pinned = MySQLConfig(**profile(tls="verify_ca", ca_file=ca_file)).connect_args()["ssl"]
    assert pinned.verify_mode == ssl.CERT_REQUIRED
    assert pinned.check_hostname is False

    verified = MySQLConfig(**profile(tls="verify", ca_file=ca_file)).connect_args()["ssl"]
    assert verified.verify_mode == ssl.CERT_REQUIRED
    assert verified.check_hostname is True


def test_configured_ca_bundle_is_the_one_loaded(tmp_path, monkeypatch):
    """Pass-through check, separate from the semantics asserted above."""
    from research_platform.core import config as config_module

    ca_file = write_ca_bundle(tmp_path / "source-ca.pem")
    loaded = []
    real_context = config_module.ssl.create_default_context

    def spy(cafile=None, **kwargs):
        loaded.append(cafile)
        return real_context(cafile=cafile, **kwargs)

    monkeypatch.setattr(config_module.ssl, "create_default_context", spy)

    MySQLConfig(**profile(tls="verify_ca", ca_file=ca_file)).connect_args()
    assert loaded == [str(ca_file), ca_file]


@pytest.mark.parametrize("tls", ["verify", "verify_ca"])
def test_strict_certificate_checks_are_relaxed_only_for_verify_ca(tmp_path, monkeypatch, tls):
    ca_file = write_ca_bundle(tmp_path / "source-ca.pem")
    real_context = ssl.create_default_context

    def strict_context(**kwargs):
        context = real_context(**kwargs)
        context.verify_flags |= ssl.VERIFY_X509_STRICT
        return context

    # Simulate Python 3.13 defaults even when this suite runs on Python 3.12.
    monkeypatch.setattr(ssl, "create_default_context", strict_context)
    context = MySQLConfig(**profile(tls=tls, ca_file=ca_file)).connect_args()["ssl"]
    assert bool(context.verify_flags & ssl.VERIFY_X509_STRICT) == (tls == "verify")
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_an_unusable_ca_bundle_is_rejected_at_configuration_time(tmp_path):
    """An unreadable bundle must fail as configuration, not as a startup crash."""
    ca_file = tmp_path / "source-ca.pem"
    ca_file.write_text("not a certificate")
    with pytest.raises(ValidationError, match="not a readable PEM bundle"):
        MySQLConfig(**profile(tls="verify_ca", ca_file=ca_file))


def test_plaintext_tls_builds_no_context_at_all():
    options = MySQLConfig(**profile(tls="disabled")).connect_args()
    assert options["ssl_disabled"] is True
    assert "ssl" not in options


@pytest.mark.parametrize(
    "changes",
    [
        {"port": 0},
        {"password": ""},
        {"read_timeout": 0},
        # Regression guard, not a typo: "prefer" (fall back to no verification)
        # must never become an accepted mode.
        {"tls": "prefer"},
        {"tls": "verify_ca"},
        {"ca_file": "missing-ca-file.pem"},
        {"tls": "disabled", "ca_file": "missing-ca-file.pem"},
        {"tls": "verify_ca", "ca_file": "missing-ca-file.pem"},
    ],
)
def test_invalid_source_configuration_is_rejected(changes):
    values = profile()
    values.update(changes)
    with pytest.raises(ValidationError):
        MySQLConfig(**values)


def test_partial_source_does_not_fall_back_to_application(monkeypatch):
    monkeypatch.setenv("RP_SOURCE_MYSQL__HOST", "incomplete.example.invalid")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_role_collision_and_ambiguous_application_config_are_rejected():
    with pytest.raises(ValidationError, match="must be separate"):
        Settings(database_mysql=profile(), source_mysql=profile(), _env_file=None)
    with pytest.raises(ValidationError, match="must be separate"):
        Settings(
            database_url="mysql+pymysql://writer:password@source.example.invalid/market",
            source_mysql=profile(),
            _env_file=None,
        )
    with pytest.raises(ValidationError, match="not both"):
        Settings(database_url="sqlite:///other.db", database_mysql=profile(), _env_file=None)


def test_engine_factories_keep_roles_separate_without_connecting(monkeypatch):
    from research_platform.core import database

    captured = []
    sentinel = object()

    def fake_engine(url, connect_args=None):
        captured.append((url, connect_args))
        return sentinel

    monkeypatch.setattr(database, "make_engine", fake_engine)
    settings = Settings(source_mysql=profile(), _env_file=None)
    assert make_application_engine(settings) is sentinel
    assert make_source_engine(settings) is sentinel
    assert isinstance(captured[0][0], str)
    assert captured[1][0].database == "market"
    assert captured[1][0].username == "reader"
    assert captured[1][1]["ssl"].check_hostname


def task_functions():
    return runpy.run_path(str(Path(__file__).resolve().parents[2] / "tools/project.py"))


def test_cli_validation_never_echoes_secret_input(monkeypatch, capsys):
    monkeypatch.setenv("RP_SOURCE_MYSQL__PASSWORD", "do-not-print-this-password")
    monkeypatch.setenv("RP_SOURCE_MYSQL__PORT", "invalid-port")
    with pytest.raises(SystemExit) as failure:
        task_functions()["database_config"]("source", False)
    assert "source_mysql" in str(failure.value)
    assert "do-not-print-this-password" not in str(failure.value)
    assert "do-not-print-this-password" not in capsys.readouterr().out


def test_offline_config_does_not_construct_an_engine(monkeypatch, capsys, tmp_path):
    from research_platform.core import database

    # The CLI reads the ambient .env through Settings. Run from an empty directory
    # so this test asserts the "source not configured" report rather than whatever
    # the developer's machine happens to have configured; exported RP_* variables
    # are already cleared for every case by the shared autouse fixture.
    monkeypatch.chdir(tmp_path)

    def fail(*args, **kwargs):
        raise AssertionError("Offline configuration must not create an engine")

    monkeypatch.setattr(database, "make_application_engine", fail)
    monkeypatch.setattr(database, "make_source_engine", fail)
    tasks = task_functions()
    tasks["database_config"]("app", False)
    tasks["database_config"]("source", False)
    assert '"configured": false' in capsys.readouterr().out


def test_local_migration_refuses_structured_application_mysql(monkeypatch):
    for key, value in profile().items():
        monkeypatch.setenv(f"RP_DATABASE_MYSQL__{key.upper()}", value)
    with pytest.raises(SystemExit, match="limited to the new local SQLite"):
        task_functions()["migrate"]()


def test_explicit_local_tls_disable_and_invalid_application_url():
    values = profile()
    values["tls"] = "disabled"
    assert MySQLConfig(**values).connect_args()["ssl_disabled"] is True
    with pytest.raises(ValidationError, match="Invalid application database URL"):
        Settings(database_url="not-a-url-with-private-password", _env_file=None)
    with pytest.raises(ValidationError, match="driver must"):
        Settings(database_url="postgresql://localhost/db", _env_file=None)


def test_auth_config_requires_a_long_secret():
    with pytest.raises(ValidationError):
        Settings(auth={"secret": "too-short"}, _env_file=None)
    settings = Settings(auth={"secret": "x" * 48}, _env_file=None)
    assert settings.auth is not None
    assert "x" * 48 not in repr(settings)


def test_production_requires_auth_and_secure_cookies():
    from research_platform.main import create_app

    with pytest.raises(RuntimeError, match="configure RP_AUTH__SECRET"):
        create_app(Settings(environment="production", database_url="sqlite://", _env_file=None))
    with pytest.raises(RuntimeError, match="COOKIE_SECURE"):
        create_app(
            Settings(
                environment="production",
                database_url="sqlite://",
                auth={"secret": "y" * 48, "cookie_secure": False},
                _env_file=None,
            )
        )


def test_object_storage_endpoint_and_secrets():
    storage = Settings(
        object_storage={
            "endpoint": "minio.local",
            "port": 9000,
            "access_key": "access-value",
            "secret_key": "secret-value",
        },
        _env_file=None,
    ).object_storage
    assert storage is not None
    assert storage.endpoint_url() == "http://minio.local:9000"
    assert "secret-value" not in repr(storage)


def test_development_start_does_not_require_auth():
    from research_platform.main import create_app

    assert create_app(Settings(environment="test", database_url="sqlite://", _env_file=None))
