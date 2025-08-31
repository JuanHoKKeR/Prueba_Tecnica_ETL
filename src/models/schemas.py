"""
Modelos Pydantic para validacion de requests/responses
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator, ConfigDict
from decimal import Decimal


class RiskLevel(str, Enum):
    """Enumeracion de niveles de riesgo"""
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class TrendDirection(str, Enum):
    """Enumeracion de direcciones de tendencia"""
    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    WORSENING = "WORSENING"


class JobStatus(str, Enum):
    """Enumeracion de estados de trabajos ETL"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProcessingMode(str, Enum):
    """Modo de procesamiento para ETL"""
    BATCH = "BATCH"
    REALTIME = "REALTIME"
    INCREMENTAL = "INCREMENTAL"


class Coordinate(BaseModel):
    """Modelo para coordenadas geograficas"""
    latitude: float = Field(..., ge=-90, le=90)  # Latitud entre -90 y 90
    longitude: float = Field(..., ge=-180, le=180)  # Longitud entre -180 y 180


class TimeRange(BaseModel):
    """Modelo para rango de tiempo en consultas de datos"""
    start_date: datetime  # Fecha de inicio
    end_date: datetime  # Fecha de fin

    @validator("end_date")
    def validate_dates(cls, v, values):
        if "start_date" in values and v < values["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v


class CrimeIncident(BaseModel):
    """Modelo para datos de incidentes de crimen"""
    incident_date: datetime  # Fecha del incidente
    incident_type: str  # Tipo de incidente
    modalidad: Optional[str] = None  # Modalidad del crimen
    localidad: Optional[str] = None  # Localidad donde ocurrio
    upz: Optional[str] = None  # UPZ donde ocurrio
    barrio: Optional[str] = None  # Barrio donde ocurrio
    zona: Optional[str] = None  # Zona general
    latitude: Optional[float] = None  # Latitud del incidente
    longitude: Optional[float] = None  # Longitud del incidente
    source: str = "SIEDCO"  # Fuente de los datos


class BikeLane(BaseModel):
    """Modelo para datos de ciclorutas"""
    lane_id: str  # ID unico de la cicloruta
    name: Optional[str] = None  # Nombre de la cicloruta
    localidad: Optional[str] = None  # Localidad donde esta
    length_km: Optional[float] = Field(None, ge=0)  # Longitud en km
    lane_type: Optional[str] = None  # Tipo de cicloruta
    condition: Optional[str] = None  # Condicion de la cicloruta
    geometry: Optional[Dict[str, Any]] = None  # Geometria en formato GeoJSON


class BikeParking(BaseModel):
    """Modelo para datos de estacionamientos de bicis"""
    parking_id: str  # ID unico del estacionamiento
    name: Optional[str] = None  # Nombre del estacionamiento
    address: Optional[str] = None  # Direccion
    localidad: Optional[str] = None  # Localidad
    upz: Optional[str] = None  # UPZ
    capacity: Optional[int] = Field(None, ge=0)  # Capacidad de bicis
    security_level: Optional[str] = None  # Nivel de seguridad
    latitude: Optional[float] = None  # Latitud
    longitude: Optional[float] = None  # Longitud
    is_public: bool = True  # Si es publico o no


class Zone(BaseModel):
    """Modelo para datos de zonas geograficas"""
    zone_code: str  # Codigo unico de la zona
    zone_type: str  # Tipo de zona (LOCALIDAD, UPZ, BARRIO)
    name: str  # Nombre de la zona
    parent_zone_code: Optional[str] = None  # Codigo de la zona padre
    area_km2: Optional[float] = Field(None, ge=0)  # Area en km2
    population: Optional[int] = Field(None, ge=0)  # Poblacion
    geometry: Optional[Dict[str, Any]] = None  # Geometria en formato GeoJSON


class SafetyMetrics(BaseModel):
    """Modelo para metricas de seguridad de una zona"""
    thefts_last_7_days: int = Field(0, ge=0)  # Robos en los ultimos 7 dias
    thefts_last_30_days: int = Field(0, ge=0)  # Robos en los ultimos 30 dias
    thefts_last_90_days: int = Field(0, ge=0)  # Robos en los ultimos 90 dias
    theft_density_per_km2: float = Field(0, ge=0)  # Densidad de robos por km2
    bike_lane_coverage_km: float = Field(0, ge=0)  # Cobertura de ciclorutas en km
    bike_lane_density_per_km2: float = Field(0, ge=0)  # Densidad de ciclorutas por km2
    safe_parking_spots: int = Field(0, ge=0)  # Numero de estacionamientos seguros
    parking_density_per_km2: float = Field(0, ge=0)  # Densidad de estacionamientos por km2


class SafetyRecommendations(BaseModel):
    """Modelo para recomendaciones de seguridad de una zona"""
    best_hours: List[str] = []  # Mejores horas para andar en bici
    safe_routes: List[str] = []  # Rutas seguras
    avoid_areas: List[str] = []  # Areas a evitar
    parking_locations: List[Dict[str, Any]] = []  # Lugares recomendados para estacionar


class ZoneSafetyScore(BaseModel):
    """Modelo completo para puntaje de seguridad de una zona"""
    zone_code: str  # Codigo de la zona
    zone_name: Optional[str] = None  # Nombre de la zona
    zone_type: Optional[str] = None  # Tipo de zona
    calculation_date: date  # Fecha del calculo
    safety_score: float = Field(..., ge=0, le=100)  # Puntaje de seguridad (0-100)
    risk_level: RiskLevel  # Nivel de riesgo
    metrics: SafetyMetrics  # Metricas de seguridad
    trend: TrendDirection = TrendDirection.STABLE  # Tendencia
    trend_percentage: Optional[float] = None  # Porcentaje de cambio en la tendencia
    recommendations: SafetyRecommendations  # Recomendaciones
    created_at: Optional[datetime] = None  # Fecha de creacion
    updated_at: Optional[datetime] = None  # Fecha de actualizacion

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            Decimal: float
        }


class ProcessRequest(BaseModel):
    """Modelo para request de procesamiento por lotes"""
    mode: ProcessingMode = ProcessingMode.BATCH  # Modo de procesamiento
    time_range: Optional[TimeRange] = None  # Rango de tiempo
    zones: List[str] = []  # Lista de zonas a procesar
    force_refresh: bool = False  # Forzar refresco de datos

    @validator("zones", pre=True)
    def validate_zones(cls, v):
        if isinstance(v, str):
            return [v]
        return v


class ProcessResponse(BaseModel):
    """Modelo para response de procesamiento por lotes"""
    job_id: str  # ID del trabajo
    status: JobStatus  # Estado del trabajo
    message: str  # Mensaje descriptivo
    started_at: datetime  # Fecha de inicio
    estimated_completion: Optional[datetime] = None  # Fecha estimada de finalizacion

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AnalyzeZoneRequest(BaseModel):
    """Modelo para request de analisis de zona"""
    zone_code: str  # Codigo de la zona a analizar
    include_historical: bool = False  # Incluir datos historicos
    days_back: int = Field(30, ge=1, le=365)  # Dias atras para analizar


class AnalyzeZoneResponse(BaseModel):
    """Modelo para response de analisis de zona"""
    zone_analysis: ZoneSafetyScore  # Analisis de la zona
    historical_trend: Optional[List[Dict[str, Any]]] = None  # Tendencia historica
    nearby_zones: Optional[List[Dict[str, Any]]] = None  # Zonas cercanas
    last_incidents: Optional[List[Dict[str, Any]]] = None  # Ultimos incidentes


class HealthResponse(BaseModel):
    """Modelo para response de health check"""
    status: str = "healthy"  # Estado del servicio
    version: str  # Version de la API
    database: str  # Estado de la base de datos
    cache: str  # Estado del cache
    timestamp: datetime  # Timestamp de la respuesta

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ErrorResponse(BaseModel):
    """Modelo para response de errores"""
    error: str  # Tipo de error
    message: str  # Mensaje de error
    details: Optional[Dict[str, Any]] = None  # Detalles adicionales
    timestamp: datetime = Field(default_factory=datetime.now)  # Timestamp del error

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )