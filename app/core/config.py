from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    silogtran_base_url: str = "https://construproyec.colombiasoftware.net"
    silogtran_login_url: str = "https://construproyec.colombiasoftware.net/index.php?page=Login"
    silogtran_log_url: str = (
        "https://construproyec.colombiasoftware.net/index.php?page=Maestros.Interfaz.BuscarLogInterfaz"
    )
    silogtran_username: str = ""
    silogtran_password: str = ""
    silogtran_cost_center: str = "CONSTRUPROYEC-PRINCIPAL"
    silogtran_keepalive_seconds: int = 240
    silogtran_session_lifetime_seconds: int = 900

    # Adaptadores: nombre real del control PRADO (vacio = deteccion por etiqueta).
    silogtran_log_interfaz_field: str = ""
    silogtran_log_datos_entrada_field: str = ""
    silogtran_log_date_start_field: str = ""
    silogtran_log_date_end_field: str = ""
    silogtran_log_verbo_field: str = ""
    silogtran_log_search_button: str = ""
    interfaces: dict[str, str] = {}

    api_token: str = ""
    admin_api_key: str = ""
    request_timeout_seconds: float = 60
    rate_limit_per_minute: int = 60
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
