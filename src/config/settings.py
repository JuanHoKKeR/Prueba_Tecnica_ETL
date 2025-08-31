"""
Configuracion de settings para el microservicio de analisis de zonas de Roda
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Settings de la aplicacion con soporte para variables de entorno"""

    # Configuracion de la API
    api_host: str = Field(default="0.0.0.0", env="API_HOST")  # Host donde corre la API
    api_port: int = Field(default=8080, env="API_PORT")  # Puerto para la API
    api_env: str = Field(default="development", env="API_ENV")  # Entorno, como desarrollo o produccion
    api_title: str = "Roda Zone Analytics API"  # Titulo de la API
    api_version: str = "1.0.0"  # Version de la API

    # Configuracion de la base de datos
    database_url: str = Field(
        default="postgresql://roda_user:123456@localhost:5432/roda_analytics",
        env="DATABASE_URL"
    )  # URL completa para conectar a Postgres
    postgres_user: str = Field(default="roda_user", env="POSTGRES_USER")  # Usuario de Postgres
    postgres_password: str = Field(default="123456", env="POSTGRES_PASSWORD")  # Contraseña de Postgres
    postgres_db: str = Field(default="roda_analytics", env="POSTGRES_DB")  # Nombre de la base de datos
    postgres_host: str = Field(default="localhost", env="POSTGRES_HOST")  # Host de Postgres
    postgres_port: int = Field(default=5432, env="POSTGRES_PORT")  # Puerto de Postgres

    # Configuracion de BigQuery (opcional)
    enable_bigquery: bool = Field(default=False, env="ENABLE_BIGQUERY")  # Habilitar BigQuery
    gcp_project_id: str = Field(default="", env="GCP_PROJECT_ID")  # ID del proyecto GCP
    bigquery_dataset: str = Field(default="roda_analytics", env="BIGQUERY_DATASET")  # Dataset de BigQuery
    bigquery_table: str = Field(default="zone_safety_scores", env="BIGQUERY_TABLE")  # Tabla de BigQuery

    # Configuracion de Scheduler (opcional)
    enable_scheduler: bool = Field(default=False, env="ENABLE_SCHEDULER")  # Habilitar actualizaciones automáticas
    schedule_cron: str = Field(default="0 6 * * *", env="SCHEDULE_CRON")  # Expresión cron para scheduler
    postgres_port: int = Field(default=5432, env="POSTGRES_PORT")  # Puerto de Postgres

    # Configuracion de GCP (Google Cloud Platform)
    gcp_project_id: Optional[str] = Field(default=None, env="GCP_PROJECT_ID")  # ID del proyecto en GCP
    gcp_region: str = Field(default="us-central1", env="GCP_REGION")  # Region de GCP
    bigquery_dataset: Optional[str] = Field(default="roda_analytics", env="BIGQUERY_DATASET")  # Dataset en BigQuery

    # APIs externas
    datos_gov_api_base: str = Field(
        default="https://www.datos.gov.co/resource",
        env="DATOS_GOV_API_BASE"
    )  # Base URL para la API de datos abiertos de Colombia

    # Configuracion del cache
    cache_ttl_seconds: int = Field(default=3600, env="CACHE_TTL_SECONDS")  # Tiempo de vida del cache en segundos
    data_cache_dir: Path = Field(default="/tmp/roda_cache", env="DATA_CACHE_DIR")  # Directorio para cache de datos

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")  # Nivel de logs, como INFO o DEBUG

    # Procesamiento de datos
    batch_size: int = 1000  # Tamaño de lotes para procesar datos
    max_retries: int = 3  # Maximo numero de reintentos
    request_timeout: int = 30  # Timeout para requests en segundos

    # Umbrales para puntajes de riesgo
    risk_thresholds: dict = {
        "VERY_LOW": (80, 100),  # Muy bajo riesgo
        "LOW": (60, 80),  # Bajo riesgo
        "MEDIUM": (40, 60),  # Riesgo medio
        "HIGH": (20, 40),  # Alto riesgo
        "VERY_HIGH": (0, 20)  # Muy alto riesgo
    }

    # URLs de fuentes de datos
    crime_api_endpoint: str = "9vha-vh9n.json"  # Endpoint para datos de crimenes
    bike_lanes_geojson_url: str = (
        "https://datosabiertos.bogota.gov.co/dataset/"
        "fe3b2925-3e76-4928-9a01-91cbd2e02f3b/resource/"
        "9b8ddc28-7f06-43a8-a2d2-6360a1a154ea/download/ciclorruta.geojson"
    )  # URL para datos de ciclorutas en GeoJSON (actualizado 2025-04-26)
    parking_csv_url: str = (
        "https://datosabiertos.bogota.gov.co/dataset/"
        "8471c407-1f36-4dbb-b627-9db9a80628c6/resource/"
        "78852fb0-883e-490c-a8d8-b649c4ef84ad/download/cicloparqueadero.geojson"
    )  # URL para datos de estacionamientos en GeoJSON (actualizado 2025-06-18)
    localidades_geojson_url: str = (
        "https://datosabiertos.bogota.gov.co/dataset/"
        "856cb657-8ca3-4ee8-857f-37211173b1f8/resource/"
        "497b8756-0927-4aee-8da9-ca4e32ca3a8a/download/loca.json"
    )  # URL para datos de localidades en JSON (actualizado 2023-02-28)
    upz_geojson_url: str = (
        "https://datosabiertos.bogota.gov.co/dataset/"
        "14a3f701-35a9-4d96-a2b5-0f38c44190ed/resource/"
        "e1893236-0de4-41bf-9757-4441c137e42f/download/macroterritorio.json"
    )  # URL para datos de UPZ/macroterritorio en JSON (actualizado 2025-08-22)

    @validator("data_cache_dir", pre=True)
    def create_cache_dir(cls, v):
        """Asegurar que el directorio de cache exista"""
        cache_dir = Path(v)
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    @property
    def is_production(self) -> bool:
        """Verificar si esta corriendo en entorno de produccion"""
        return self.api_env.lower() == "production"

    @property
    def is_gcp_enabled(self) -> bool:
        """Verificar si los servicios de GCP estan configurados"""
        return self.gcp_project_id is not None

    def get_database_url(self, async_mode: bool = True) -> str:
        """Obtener URL de base de datos con el driver apropiado"""
        if async_mode:
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://")
        return self.database_url

    class Config:
        env_file = ".env"  # Archivo de variables de entorno
        env_file_encoding = "utf-8"  # Codificacion del archivo
        case_sensitive = False  # No sensible a mayusculas


# Crear instancia global de settings
settings = Settings()