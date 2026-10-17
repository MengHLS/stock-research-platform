from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RP_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = SecretStr("sqlite:///.scratch/development.db")

    def require_development_release(self) -> None:
        if self.environment == "production":
            raise RuntimeError(
                "Production is blocked: implement real authentication, resource authorization "
                "and deployment acceptance before releasing this starter."
            )
