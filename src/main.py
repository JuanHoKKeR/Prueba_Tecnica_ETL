"""
API de analisis de zonas de Roda - Aplicacion principal de FastAPI
"""

import logging
import uuid
import warnings
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
import uvicorn

from .config.settings import settings
from .models.schemas import (
    ProcessRequest, ProcessResponse, JobStatus,
    AnalyzeZoneRequest, AnalyzeZoneResponse,
    HealthResponse, ErrorResponse, ZoneSafetyScore
)
from .etl.extract import DataExtractor
from .etl.transform import DataTransformer
from .etl.load import DataLoader
from .services.anomaly_detection import ZoneAnomalyDetector, analyze_with_ml


# Suprimir warnings molestos de fiona
warnings.filterwarnings("ignore", category=UserWarning, module="fiona.ogrext")
warnings.filterwarnings("ignore", message=".*Expecting property name enclosed in double quotes.*")

# Configurar logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suprimir logs específicos que son molestos
logging.getLogger("fiona.ogrext").setLevel(logging.ERROR)


# Tracker global de trabajos (en produccion, usar Redis o base de datos)
job_tracker: Dict[str, Dict] = {}


def get_optimal_date_range():
    """
    Determinar el rango de fechas óptimo basado en datos disponibles
    
    Returns:
        tuple: (start_date, end_date) con el rango más reciente disponible
    """
    # Datos reales disponibles: enero-junio 2025
    # Para análisis completo usamos todo el período
    return datetime(2025, 1, 1), datetime(2025, 6, 30)


def get_recent_analysis_range():
    """
    Obtener rango para análisis reciente (últimos 3 meses de datos)
    
    Returns:
        tuple: (start_date, end_date) para análisis de tendencias recientes
    """
    # Últimos 3 meses del período con datos
    return datetime(2025, 4, 1), datetime(2025, 6, 30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manejar el ciclo de vida de la aplicacion
    """
    # Inicio
    logger.info("Iniciando API de analisis de zonas de Roda")

    # Probar conexion a la base de datos
    async with DataLoader() as loader:
        if await loader.test_connection():
            logger.info("Conexion a la base exitosa")
        else:
            logger.error("Conexion a la base fallo")

    yield

    # Apagado
    logger.info("Apagando API de analisis de zonas de Roda")


# Crear aplicacion FastAPI
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="Microservicio para analizar seguridad de zonas para vehiculos electricos de Roda",
    lifespan=lifespan
)

# Agregar middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En produccion, especificar origenes permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def run_etl_pipeline(
    job_id: str,
    request: ProcessRequest
):
    """
    Ejecutar el pipeline ETL completo

    Args:
        job_id: Identificador del trabajo
        request: Parametros del request de procesamiento
    """
    try:
        logger.info(f"Iniciando pipeline ETL para trabajo {job_id}")
        job_tracker[job_id]["status"] = JobStatus.RUNNING

        # Determinar rango de tiempo
        if request.time_range:
            start_date = request.time_range.start_date
            end_date = request.time_range.end_date
        else:
            # Usar el rango óptimo de datos disponibles
            start_date, end_date = get_optimal_date_range()

        # Extraer datos
        logger.info(f"Extrayendo datos desde {start_date} hasta {end_date}")
        async with DataExtractor() as extractor:
            data = await extractor.fetch_all_data(
                start_date=start_date,
                end_date=end_date,
                use_cache=not request.force_refresh
            )

        # Transformar datos usando datos reales de criminalidad
        logger.info("Transformando datos y calculando puntajes de seguridad con datos reales")
        transformer = DataTransformer()
        scores = transformer.transform_all_zones_with_real_data(data, datetime.now())

        # Filtrar por zonas solicitadas si se especifican
        if request.zones:
            scores = [s for s in scores if s.zone_code in request.zones]

        # Cargar datos
        logger.info(f"Cargando {len(scores)} puntajes de zona a la base de datos")
        
        # Crear registro de trabajo antes de cargar
        async with DataLoader() as loader:
            db_job_id = await loader.create_job(
                job_type="BATCH_PROCESS",
                metadata={"request": request.dict()}
            )

            # Verificar si existen zonas, si no cargarlas
            if not await loader.zones_exist() or request.force_refresh:
                logger.info("Cargando datos de zonas a la base de datos")
                await loader.load_zones(data['localidades'])

        # Cargar puntajes usando load_data que incluye BigQuery
        from .etl.load import load_data
        records = await load_data(scores, data['localidades'], db_job_id)

        # Actualizar tracker de trabajos
        job_tracker[job_id]["status"] = JobStatus.COMPLETED
        job_tracker[job_id]["completed_at"] = datetime.now()
        job_tracker[job_id]["records_processed"] = records
        job_tracker[job_id]["message"] = f"Procesadas exitosamente {records} zonas"

        logger.info(f"Pipeline ETL completado para trabajo {job_id}")

    except Exception as e:
        logger.error(f"Pipeline ETL fallo para trabajo {job_id}: {e}")
        job_tracker[job_id]["status"] = JobStatus.FAILED
        job_tracker[job_id]["error"] = str(e)
        job_tracker[job_id]["completed_at"] = datetime.now()


@app.get("/", response_model=Dict[str, str])
async def root():
    """
    Endpoint raiz
    """
    return {
        "message": "API de analisis de zonas de Roda",
        "version": settings.api_version,
        "docs": "/docs"
    }


@app.get("/data-availability")
async def get_data_availability():
    """
    Obtener información sobre la disponibilidad de datos
    
    Retorna los rangos de fechas disponibles para análisis
    """
    optimal_start, optimal_end = get_optimal_date_range()
    recent_start, recent_end = get_recent_analysis_range()
    
    return {
        "data_source": "Bogotá Open Data Portal - DAILoc Crime Dataset",
        "coverage": {
            "full_range": {
                "start_date": optimal_start.isoformat(),
                "end_date": optimal_end.isoformat(),
                "description": "Período completo con datos de criminalidad disponibles"
            },
            "recent_range": {
                "start_date": recent_start.isoformat(), 
                "end_date": recent_end.isoformat(),
                "description": "Últimos 3 meses para análisis de tendencias recientes"
            }
        },
        "crime_types": [
            "HURTO A PERSONAS", "HURTO A CELULARES", "HURTO A MOTOCICLETAS",
            "HURTO A BICICLETAS", "HURTO A VEHICULOS", "HURTO A ENTIDADES COMERCIALES",
            "HURTO A RESIDENCIAS", "HURTO A ENTIDADES FINANCIERAS",
            "LESIONES PERSONALES", "VIOLENCIA INTRAFAMILIAR", "SECUESTRO"
        ],
        "geographical_coverage": "20 localidades de Bogotá D.C.",
        "update_frequency": "Los datos se actualizan según disponibilidad del portal oficial",
        "recommendation": "Para análisis completos use el rango completo, para tendencias use el rango reciente"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Endpoint de health check
    """
    health_status = {
        "status": "healthy",
        "version": settings.api_version,
        "database": "unknown",
        "cache": "healthy",
        "timestamp": datetime.now()
    }

    # Revisar base de datos
    try:
        async with DataLoader() as loader:
            if await loader.test_connection():
                health_status["database"] = "healthy"
            else:
                health_status["database"] = "unhealthy"
                health_status["status"] = "degraded"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    return HealthResponse(**health_status)


@app.post("/process", response_model=ProcessResponse)
async def process_batch(
    request: ProcessRequest,
    background_tasks: BackgroundTasks
):
    """
    Procesar datos en modo lote

    Este endpoint dispara un pipeline ETL para:
    1. Extraer datos de crimen, infraestructura y zonas
    2. Calcular puntajes de seguridad para cada zona
    3. Almacenar resultados en PostgreSQL (y opcionalmente BigQuery)

    El proceso corre de forma asincrona en segundo plano.
    """
    # Generar ID de trabajo
    job_id = str(uuid.uuid4())

    # Inicializar tracker de trabajo
    job_tracker[job_id] = {
        "job_id": job_id,
        "status": JobStatus.PENDING,
        "started_at": datetime.now(),
        "message": "Trabajo en cola para procesamiento"
    }

    # Agregar a tareas en segundo plano
    background_tasks.add_task(run_etl_pipeline, job_id, request)

    # Estimar tiempo de completacion (estimacion aproximada basada en numero de zonas)
    zone_count = len(request.zones) if request.zones else 20  # Por defecto localidades
    estimated_seconds = zone_count * 2  # ~2 segundos por zona
    estimated_completion = datetime.now() + timedelta(seconds=estimated_seconds)

    return ProcessResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="Procesamiento iniciado en segundo plano",
        started_at=datetime.now(),
        estimated_completion=estimated_completion
    )


@app.get("/process/{job_id}", response_model=ProcessResponse)
async def get_job_status(job_id: str):
    """
    Obtener estado de un trabajo de procesamiento
    """
    if job_id not in job_tracker:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")

    job = job_tracker[job_id]

    return ProcessResponse(
        job_id=job_id,
        status=job["status"],
        message=job.get("message", "Procesando"),
        started_at=job["started_at"],
        estimated_completion=job.get("completed_at")
    )


@app.get("/analyze/{zone_code}", response_model=AnalyzeZoneResponse)
async def analyze_zone(
    zone_code: str,
    include_historical: bool = Query(False, description="Incluir datos de tendencias historicas"),
    days_back: int = Query(30, ge=1, le=365, description="Dias de historia a incluir")
):
    """
    Analizar seguridad de una zona especifica en tiempo real

    Este endpoint proporciona:
    - Puntaje de seguridad actual y nivel de riesgo
    - Metricas de seguridad (robos, infraestructura)
    - Recomendaciones para rutas seguras y estacionamiento
    - Tendencias historicas (opcional)
    """
    try:
        async with DataLoader() as loader:
            # Obtener ultimo puntaje para la zona
            scores = await loader.get_latest_scores(zone_code=zone_code, limit=1)

            if not scores:
                # Si no hay puntaje cacheado, calcular en tiempo real
                logger.info(f"No hay puntaje cacheado para {zone_code}, calculando en tiempo real")

                # Extraer datos recientes
                async with DataExtractor() as extractor:
                    # Usar rango optimizado para análisis reciente
                    start_date, end_date = get_recent_analysis_range()
                    data = await extractor.fetch_all_data(start_date, end_date)

                # Transformar y calcular puntaje usando datos reales
                transformer = DataTransformer()
                all_scores = transformer.transform_all_zones_with_real_data(data)

                # Encontrar zona solicitada
                zone_score = next((s for s in all_scores if s.zone_code == zone_code), None)

                if not zone_score:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Zona {zone_code} no encontrada"
                    )
            else:
                # Convertir registro de base de datos a ZoneSafetyScore
                score_data = scores[0]
                zone_score = ZoneSafetyScore(
                    zone_code=score_data['zone_code'],
                    zone_name=score_data.get('zone_name'),
                    zone_type=score_data.get('zone_type'),
                    calculation_date=score_data['calculation_date'],
                    safety_score=float(score_data['safety_score']),
                    risk_level=score_data['risk_level'],
                    metrics={
                        'thefts_last_7_days': score_data.get('thefts_last_7_days', 0),
                        'thefts_last_30_days': score_data.get('thefts_last_30_days', 0),
                        'thefts_last_90_days': score_data.get('thefts_last_90_days', 0),
                        'theft_density_per_km2': float(score_data.get('theft_density_per_km2', 0)),
                        'bike_lane_coverage_km': float(score_data.get('bike_lane_coverage_km', 0)),
                        'bike_lane_density_per_km2': float(score_data.get('bike_lane_density_per_km2', 0)),
                        'safe_parking_spots': score_data.get('safe_parking_spots', 0),
                        'parking_density_per_km2': float(score_data.get('parking_density_per_km2', 0))
                    },
                    trend=score_data.get('trend', 'STABLE'),
                    trend_percentage=float(score_data.get('trend_percentage', 0)),
                    recommendations={
                        'best_hours': score_data.get('best_hours', []),
                        'safe_routes': score_data.get('safe_routes', []),
                        'avoid_areas': score_data.get('avoid_areas', []),
                        'parking_locations': score_data.get('parking_locations', [])
                    }
                )

        # Preparar respuesta
        response = AnalyzeZoneResponse(zone_analysis=zone_score)

        # Agregar datos historicos si se solicita
        if include_historical:
            # Aqui se obtendrian datos historicos
            response.historical_trend = []

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analizando zona {zone_code}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error analizando zona: {str(e)}"
        )


@app.get("/zones", response_model=List[Dict])
async def list_zones(
    risk_level: Optional[str] = Query(None, description="Filtrar por nivel de riesgo"),
    limit: int = Query(20, ge=1, le=100, description="Maximo zonas a retornar"),
    offset: int = Query(0, ge=0, description="Offset para paginacion")
):
    """
    Listar todas las zonas con sus puntajes de seguridad actuales

    Retorna zonas ordenadas por puntaje de seguridad (mas peligrosas primero)
    """
    try:
        async with DataLoader() as loader:
            scores = await loader.get_latest_scores(limit=limit)

            # Filtrar por nivel de riesgo si se especifica
            if risk_level:
                scores = [s for s in scores if s.get('risk_level') == risk_level]

            return scores

    except Exception as e:
        logger.error(f"Error listando zonas: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listando zonas: {str(e)}"
        )


@app.get("/recommendations/safe-routes")
async def get_safe_routes(
    origin_zone: str = Query(..., description="Codigo de zona origen"),
    destination_zone: str = Query(..., description="Codigo de zona destino")
):
    """
    Obtener recomendaciones de rutas seguras entre dos zonas

    Esto integraria con servicios de rutas para sugerir
    el camino mas seguro basado en datos de crimen e infraestructura
    """
    # Implementacion simplificada
    return {
        "origin": origin_zone,
        "destination": destination_zone,
        "recommended_routes": [
            {
                "name": "Ruta Ciclovia Principal",
                "safety_score": 85,
                "distance_km": 5.2,
                "estimated_time_min": 18,
                "features": ["Ciclovia segregada", "Bien iluminada", "Alto trafico de ciclistas"]
            },
            {
                "name": "Ruta Parques",
                "safety_score": 78,
                "distance_km": 6.1,
                "estimated_time_min": 22,
                "features": ["Atraviesa parques", "Menor trafico vehicular"]
            }
        ],
        "avoid_areas": ["Zona Industrial Norte despues de 7 PM"],
        "best_time": "6:00 AM - 8:00 AM"
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """
    Manejar excepciones HTTP
    """
    error_response = ErrorResponse(
        error=f"HTTP {exc.status_code}",
        message=exc.detail,
        timestamp=datetime.now()
    )
    # Convertir manualmente el timestamp a string
    response_dict = error_response.dict()
    response_dict['timestamp'] = response_dict['timestamp'].isoformat()
    
    return JSONResponse(
        status_code=exc.status_code,
        content=response_dict
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """
    Manejar excepciones generales
    """
    logger.error(f"Excepcion no manejada: {exc}")
    error_response = ErrorResponse(
        error="Internal Server Error",
        message="Ocurrio un error inesperado",
        details={"error": str(exc)} if not settings.is_production else None,
        timestamp=datetime.now()
    )
    # Convertir manualmente el timestamp a string
    response_dict = error_response.dict()
    response_dict['timestamp'] = response_dict['timestamp'].isoformat()
    
    return JSONResponse(
        status_code=500,
        content=response_dict
    )
    
    
@app.get("/ml/anomalies")
async def detect_anomalies():
    """
    Detecta zonas con comportamiento anómalo usando Isolation Forest
    
    Útil para identificar zonas que requieren atención especial
    """
    try:
        async with DataLoader() as loader:
            # Obtener todos los scores actuales
            scores = await loader.get_latest_scores(limit=100)
            
            if not scores:
                raise HTTPException(
                    status_code=404,
                    detail="No data available for anomaly detection"
                )
            
            # Convertir a DataFrame
            df = pd.DataFrame(scores)
            
            # Detectar anomalías
            detector = ZoneAnomalyDetector()
            anomalies = detector.detect_theft_anomalies(df)
            
            return {
                "analysis_type": "anomaly_detection",
                "timestamp": datetime.now(),
                "results": anomalies,
                "summary": {
                    "total_zones_analyzed": anomalies.get("total_zones", 0),
                    "anomalous_zones_found": anomalies.get("anomalous_zones", 0),
                    "action_required": anomalies.get("anomalous_zones", 0) > 0
                }
            }
            
    except Exception as e:
        logger.error(f"Error in anomaly detection: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error detecting anomalies: {str(e)}"
        )


@app.get("/ml/clusters")
async def cluster_zones(n_clusters: int = Query(4, ge=2, le=10)):
    """
    Agrupa zonas similares usando K-Means clustering
    
    Permite estrategias diferenciadas por tipo de zona
    """
    try:
        async with DataLoader() as loader:
            scores = await loader.get_latest_scores(limit=100)
            
            if not scores or len(scores) < n_clusters:
                raise HTTPException(
                    status_code=404,
                    detail=f"Insufficient data for {n_clusters} clusters"
                )
            
            df = pd.DataFrame(scores)
            
            detector = ZoneAnomalyDetector()
            clusters = detector.cluster_zones(df, n_clusters=n_clusters)
            
            return {
                "analysis_type": "clustering",
                "timestamp": datetime.now(),
                "results": clusters,
                "summary": {
                    "optimal_clusters": clusters.get("optimal_clusters", n_clusters),
                    "zones_analyzed": len(df),
                    "insights": generate_cluster_insights(clusters)
                }
            }
            
    except Exception as e:
        logger.error(f"Error in clustering: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error clustering zones: {str(e)}"
        )


@app.get("/ml/predict/{zone_code}")
async def predict_zone_trend(
    zone_code: str,
    days_ahead: int = Query(30, ge=7, le=90)
):
    """
    Predice la tendencia futura de una zona usando regresión lineal
    
    Útil para anticipar mejoras o deterioros en seguridad
    """
    try:
        async with DataLoader() as loader:
            # Obtener histórico de la zona
            async with loader.async_session() as session:
                query = text("""
                    SELECT * FROM zone_safety_scores 
                    WHERE zone_code = :zone_code
                    ORDER BY calculation_date DESC
                    LIMIT 30
                """)
                
                result = await session.execute(query, {"zone_code": zone_code})
                rows = result.fetchall()
                
                if len(rows) < 3:
                    raise HTTPException(
                        status_code=404,
                        detail="Insufficient historical data for prediction"
                    )
                
                # Convertir a DataFrame
                import pandas as pd
                df = pd.DataFrame([dict(row._mapping) for row in rows])
                
                detector = ZoneAnomalyDetector()
                prediction = detector.predict_trend(zone_code, df)
                
                return {
                    "analysis_type": "trend_prediction",
                    "zone": zone_code,
                    "timestamp": datetime.now(),
                    "prediction": prediction,
                    "visualization_data": {
                        "historical": df[['calculation_date', 'thefts_last_30_days']].to_dict('records'),
                        "predicted_point": {
                            "date": (datetime.now() + timedelta(days=days_ahead)).date(),
                            "predicted_thefts": prediction.get("predicted_thefts_30d", 0)
                        }
                    }
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error predicting trend for {zone_code}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error predicting trend: {str(e)}"
        )


@app.get("/ml/insights")
async def get_ml_insights():
    """
    Obtiene insights combinados de todos los análisis ML
    
    Proporciona recomendaciones estratégicas basadas en IA
    """
    try:
        insights = {
            "timestamp": datetime.now(),
            "insights": [],
            "recommendations": []
        }
        
        # 1. Anomalías
        anomalies_response = await detect_anomalies()
        if anomalies_response["results"].get("anomalous_zones", 0) > 0:
            insights["insights"].append({
                "type": "ANOMALY",
                "priority": "HIGH",
                "message": f"{anomalies_response['results']['anomalous_zones']} zonas requieren atención inmediata",
                "zones": [a["zone"] for a in anomalies_response["results"]["anomalies"]]
            })
        
        # 2. Clusters
        clusters_response = await cluster_zones(n_clusters=4)
        high_value_clusters = [
            c for c in clusters_response["results"]["clusters"].values()
            if c["avg_safety_score"] > 70
        ]
        
        if high_value_clusters:
            insights["insights"].append({
                "type": "OPPORTUNITY",
                "priority": "MEDIUM",
                "message": f"{len(high_value_clusters)} grupos de zonas óptimas para expansión",
                "zones": [z for c in high_value_clusters for z in c["zones"]]
            })
        
        # 3. Recomendaciones estratégicas
        insights["recommendations"] = [
            {
                "strategy": "EXPANSION",
                "zones": [z for c in high_value_clusters for z in c["zones"]][:5],
                "rationale": "Zonas con mejor balance riesgo-infraestructura"
            },
            {
                "strategy": "RISK_MITIGATION",
                "zones": [a["zone"] for a in anomalies_response["results"].get("anomalies", [])][:3],
                "rationale": "Requieren medidas de seguridad adicionales"
            }
        ]
        
        return insights
        
    except Exception as e:
        logger.error(f"Error generating ML insights: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating insights: {str(e)}"
        )


def generate_cluster_insights(clusters: Dict) -> List[str]:
    """Helper para generar insights de clusters"""
    insights = []
    
    if not clusters.get("clusters"):
        return insights
    
    # Analizar distribución de clusters
    cluster_sizes = [c["size"] for c in clusters["clusters"].values()]
    avg_scores = [c["avg_safety_score"] for c in clusters["clusters"].values()]
    
    # Insight sobre balance
    if max(cluster_sizes) > sum(cluster_sizes) * 0.5:
        insights.append("Desbalance detectado: un cluster domina la distribución")
    
    # Insight sobre oportunidades
    high_score_zones = sum(1 for score in avg_scores if score > 70)
    if high_score_zones > 0:
        insights.append(f"{high_score_zones} clusters identificados como oportunidades de expansión")
    
    # Insight sobre riesgos
    low_score_zones = sum(1 for score in avg_scores if score < 40)
    if low_score_zones > 0:
        insights.append(f"{low_score_zones} clusters requieren estrategia de mitigación de riesgo")
    
    return insights


# Ejecutar la aplicacion
if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_env == "development",
        log_level=settings.log_level.lower()
    )