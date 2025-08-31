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
        "bf351d91-a925-455e-a51f-c1154a066c23/resource/"
        "69094859-b7a9-42e8-b201-e10ae70a6ae3/download/cicloruta.geojson"
    )  # URL para datos de ciclorutas en GeoJSON
    parking_csv_url: str = (
        "https://datosabiertos.bogota.gov.co/dataset/"
        "2f9d99a03ddf441c94ceb0e2e6f76cac_0/resource/"
        "2f9d99a03ddf441c94ceb0e2e6f76cac/download/biciparqueaderos.csv"
    )  # URL para datos de estacionamientos en CSV
    localidades_geojson_url: str = (
        "https://datosabiertos.bogota.gov.co/dataset/"
        "6d2d5e91-75c5-44d2-b5ec-7a326a0a5a6d/resource/"
        "e7919b21-0ce7-4efc-9e21-db7a8e49d9f4/download/localidad.geojson"
    )  # URL para datos de localidades en GeoJSON
    upz_geojson_url: str = (
        "https://datosabiertos.bogota.gov.co/dataset/"
        "c24beed0-458c-487e-85ac-d606343d1a51/resource/"
        "f1c47c03-e158-4872-99f3-af43a1361354/download/upz.geojson"
    )  # URL para datos de UPZ en GeoJSON

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