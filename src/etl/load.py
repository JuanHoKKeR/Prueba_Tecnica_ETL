"""
Modulo para carga de datos a PostgreSQL y BigQuery
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

import asyncpg
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import pandas as pd

from ..config.settings import settings
from ..models.schemas import ZoneSafetyScore, JobStatus

logger = logging.getLogger(__name__)


class DataLoader:
    """Clase para manejar carga de datos a PostgreSQL y BigQuery"""

    def __init__(self):
        self.db_url = settings.get_database_url(async_mode=True)  # URL de la base de datos async
        self.engine = None  # Motor de SQLAlchemy
        self.async_session = None  # Sesion async

    async def __aenter__(self):
        """Entrada al context manager async"""
        self.engine = create_async_engine(self.db_url, echo=False)
        self.async_session = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Salida del context manager async"""
        if self.engine:
            await self.engine.dispose()

    async def test_connection(self) -> bool:
        """
        Probar conexion a la base de datos

        Returns:
            True si la conexion es exitosa, False si no
        """
        try:
            async with self.engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error(f"Fallo en la conexion a la base: {e}")
            return False

    async def zones_exist(self) -> bool:
        """
        Verificar si existen zonas en la base de datos

        Returns:
            True si existen zonas, False si no
        """
        try:
            async with self.async_session() as session:
                result = await session.execute(text("SELECT COUNT(*) FROM zones"))
                count = result.scalar()
                return count > 0
        except Exception as e:
            logger.error(f"Error verificando zonas: {e}")
            return False

    async def load_zone_safety_scores(
        self,
        scores: List[ZoneSafetyScore],
        job_id: Optional[str] = None
    ) -> int:
        """
        Cargar puntajes de seguridad de zonas a PostgreSQL

        Args:
            scores: Lista de objetos ZoneSafetyScore
            job_id: ID opcional del trabajo para rastreo

        Returns:
            Numero de registros insertados
        """
        if not scores:
            logger.warning("No hay puntajes para cargar")
            return 0

        inserted = 0

        async with self.async_session() as session:
            try:
                for score in scores:
                    # Preparar datos para insercion
                    insert_query = text("""
                        INSERT INTO zone_safety_scores (
                            zone_code, calculation_date, safety_score, risk_level,
                            thefts_last_7_days, thefts_last_30_days, thefts_last_90_days,
                            theft_density_per_km2, bike_lane_coverage_km, bike_lane_density_per_km2,
                            safe_parking_spots, parking_density_per_km2, trend, trend_percentage,
                            best_hours, safe_routes, avoid_areas, parking_locations,
                            created_at, updated_at
                        ) VALUES (
                            :zone_code, :calculation_date, :safety_score, :risk_level,
                            :thefts_7d, :thefts_30d, :thefts_90d, :theft_density,
                            :bike_lane_km, :bike_lane_density, :parking_spots, :parking_density,
                            :trend, :trend_pct, :best_hours, :safe_routes, :avoid_areas,
                            :parking_locations, :created_at, :updated_at
                        )
                        ON CONFLICT (zone_code, calculation_date)
                        DO UPDATE SET
                            safety_score = EXCLUDED.safety_score,
                            risk_level = EXCLUDED.risk_level,
                            thefts_last_7_days = EXCLUDED.thefts_last_7_days,
                            thefts_last_30_days = EXCLUDED.thefts_last_30_days,
                            thefts_last_90_days = EXCLUDED.thefts_last_90_days,
                            theft_density_per_km2 = EXCLUDED.theft_density_per_km2,
                            bike_lane_coverage_km = EXCLUDED.bike_lane_coverage_km,
                            bike_lane_density_per_km2 = EXCLUDED.bike_lane_density_per_km2,
                            safe_parking_spots = EXCLUDED.safe_parking_spots,
                            parking_density_per_km2 = EXCLUDED.parking_density_per_km2,
                            trend = EXCLUDED.trend,
                            trend_percentage = EXCLUDED.trend_percentage,
                            best_hours = EXCLUDED.best_hours,
                            safe_routes = EXCLUDED.safe_routes,
                            avoid_areas = EXCLUDED.avoid_areas,
                            parking_locations = EXCLUDED.parking_locations,
                            updated_at = EXCLUDED.updated_at
                    """)

                    params = {
                        'zone_code': score.zone_code,
                        'calculation_date': score.calculation_date,
                        'safety_score': score.safety_score,
                        'risk_level': score.risk_level.value,
                        'thefts_7d': score.metrics.thefts_last_7_days,
                        'thefts_30d': score.metrics.thefts_last_30_days,
                        'thefts_90d': score.metrics.thefts_last_90_days,
                        'theft_density': score.metrics.theft_density_per_km2,
                        'bike_lane_km': score.metrics.bike_lane_coverage_km,
                        'bike_lane_density': score.metrics.bike_lane_density_per_km2,
                        'parking_spots': score.metrics.safe_parking_spots,
                        'parking_density': score.metrics.parking_density_per_km2,
                        'trend': score.trend.value,
                        'trend_pct': score.trend_percentage,
                        'best_hours': json.dumps(score.recommendations.best_hours),
                        'safe_routes': json.dumps(score.recommendations.safe_routes),
                        'avoid_areas': json.dumps(score.recommendations.avoid_areas),
                        'parking_locations': json.dumps(score.recommendations.parking_locations),
                        'created_at': score.created_at or datetime.now(),
                        'updated_at': score.updated_at or datetime.now()
                    }

                    await session.execute(insert_query, params)
                    inserted += 1

                await session.commit()
                logger.info(f"Cargados exitosamente {inserted} puntajes de seguridad de zonas")

                # Actualizar estado del trabajo si se proporciona
                if job_id:
                    await self.update_job_status(
                        job_id,
                        JobStatus.COMPLETED,
                        records_processed=inserted
                    )

                return inserted

            except Exception as e:
                logger.error(f"Error cargando puntajes de seguridad: {e}")
                await session.rollback()

                if job_id:
                    await self.update_job_status(
                        job_id,
                        JobStatus.FAILED,
                        error_message=str(e)
                    )
                raise

    async def load_zones(self, zones_gdf) -> int:
        """
        Cargar limites de zonas a PostgreSQL

        Args:
            zones_gdf: GeoDataFrame con limites de zonas

        Returns:
            Numero de zonas cargadas
        """
        inserted = 0

        async with self.async_session() as session:
            try:
                for idx, zone in zones_gdf.iterrows():
                    # Convertir geometria a WKT para PostGIS
                    geom_wkt = zone.geometry.wkt if zone.geometry else None

                    insert_query = text("""
                        INSERT INTO zones (
                            zone_code, zone_type, name, area_km2, geometry
                        ) VALUES (
                            :zone_code, :zone_type, :name, :area,
                            ST_GeomFromText(:geometry, 4326)
                        )
                        ON CONFLICT (zone_code) DO UPDATE SET
                            name = EXCLUDED.name,
                            area_km2 = EXCLUDED.area_km2,
                            geometry = EXCLUDED.geometry
                    """)

                    params = {
                        'zone_code': zone.get('LocNombre', f'Zone_{idx}'),
                        'zone_type': 'LOCALIDAD',
                        'name': zone.get('LocNombre', f'Zone_{idx}'),
                        'area': zone.get('area_km2', 0),
                        'geometry': geom_wkt
                    }

                    await session.execute(insert_query, params)
                    inserted += 1

                await session.commit()
                logger.info(f"Cargadas exitosamente {inserted} zonas")
                return inserted

            except Exception as e:
                logger.error(f"Error cargando zonas: {e}")
                await session.rollback()
                raise

    async def create_job(self, job_type: str, metadata: Dict = None) -> str:
        """
        Crear un nuevo registro de trabajo ETL

        Args:
            job_type: Tipo de trabajo
            metadata: Diccionario opcional de metadata

        Returns:
            ID del trabajo
        """
        async with self.async_session() as session:
            try:
                query = text("""
                    INSERT INTO etl_jobs (job_type, status, metadata)
                    VALUES (:job_type, :status, :metadata)
                    RETURNING job_id
                """)

                params = {
                    'job_type': job_type,
                    'status': JobStatus.RUNNING.value,
                    'metadata': json.dumps(metadata) if metadata else None
                }

                result = await session.execute(query, params)
                job_id = result.scalar()
                await session.commit()

                logger.info(f"Creado trabajo {job_id} de tipo {job_type}")
                return str(job_id)

            except Exception as e:
                logger.error(f"Error creando trabajo: {e}")
                await session.rollback()
                raise

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        records_processed: int = 0,
        error_message: str = None
    ):
        """
        Actualizar estado de trabajo ETL

        Args:
            job_id: ID del trabajo
            status: Nuevo estado
            records_processed: Numero de registros procesados
            error_message: Mensaje de error si fallo
        """
        async with self.async_session() as session:
            try:
                query = text("""
                    UPDATE etl_jobs
                    SET status = :status,
                        completed_at = :completed_at,
                        records_processed = :records,
                        error_message = :error
                    WHERE job_id = :job_id
                """)

                params = {
                    'job_id': job_id,
                    'status': status.value,
                    'completed_at': datetime.now() if status in [JobStatus.COMPLETED, JobStatus.FAILED] else None,
                    'records': records_processed,
                    'error': error_message
                }

                await session.execute(query, params)
                await session.commit()

                logger.info(f"Actualizado estado del trabajo {job_id} a {status.value}")

            except Exception as e:
                logger.error(f"Error actualizando estado del trabajo: {e}")
                await session.rollback()

    async def get_latest_scores(
        self,
        zone_code: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Obtener los ultimos puntajes de seguridad de la base de datos

        Args:
            zone_code: Zona especifica opcional para filtrar
            limit: Maximo numero de registros

        Returns:
            Lista de diccionarios de puntajes
        """
        async with self.async_session() as session:
            try:
                if zone_code:
                    query = text("""
                        SELECT * FROM v_current_safety_scores
                        WHERE zone_code = :zone_code
                        LIMIT :limit
                    """)
                    params = {'zone_code': zone_code, 'limit': limit}
                else:
                    query = text("""
                        SELECT * FROM v_current_safety_scores
                        ORDER BY safety_score ASC
                        LIMIT :limit
                    """)
                    params = {'limit': limit}

                result = await session.execute(query, params)
                rows = result.fetchall()

                # Convertir a diccionarios
                scores = []
                for row in rows:
                    scores.append(dict(row._mapping))

                return scores

            except Exception as e:
                logger.error(f"Error obteniendo puntajes: {e}")
                raise

    async def load_to_bigquery(
        self,
        scores: List[ZoneSafetyScore],
        table_id: str = "zone_safety_scores"
    ) -> int:
        """
        Cargar datos a BigQuery

        Args:
            scores: Lista de objetos ZoneSafetyScore
            table_id: ID de tabla de BigQuery

        Returns:
            Numero de registros cargados
        """
        if not settings.is_gcp_enabled:
            logger.info("BigQuery no configurado, saltando")
            return 0

        if not scores:
            logger.info("No hay puntajes para cargar a BigQuery")
            return 0

        try:
            from google.cloud import bigquery

            client = bigquery.Client(project=settings.gcp_project_id)
            table_ref = f"{settings.gcp_project_id}.{settings.bigquery_dataset}.{table_id}"

            # Convertir puntajes a DataFrame
            records = []
            for score in scores:
                record = {
                    'zone_code': score.zone_code,
                    'zone_name': score.zone_name,
                    'calculation_date': score.calculation_date.isoformat(),
                    'safety_score': score.safety_score,
                    'risk_level': score.risk_level.value,
                    'thefts_30d': score.metrics.thefts_last_30_days,
                    'trend': score.trend.value,
                    'created_at': score.created_at.isoformat() if score.created_at else None
                }
                records.append(record)

            df = pd.DataFrame(records)

            # Cargar a BigQuery
            job_config = bigquery.LoadJobConfig(
                write_disposition="WRITE_APPEND",
                schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
                schema=[
                    bigquery.SchemaField("zone_code", "STRING", mode="REQUIRED"),
                    bigquery.SchemaField("zone_name", "STRING", mode="REQUIRED"),
                    bigquery.SchemaField("calculation_date", "TIMESTAMP", mode="REQUIRED"),
                    bigquery.SchemaField("safety_score", "FLOAT", mode="REQUIRED"),
                    bigquery.SchemaField("risk_level", "STRING", mode="REQUIRED"),
                    bigquery.SchemaField("thefts_30d", "INTEGER", mode="NULLABLE"),
                    bigquery.SchemaField("trend", "STRING", mode="NULLABLE"),
                    bigquery.SchemaField("created_at", "TIMESTAMP", mode="NULLABLE"),
                ]
            )

            job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
            job.result()  # Esperar a que termine el trabajo

            logger.info(f"Cargados {len(records)} registros a tabla de BigQuery {table_ref}")
            return len(records)

        except ImportError:
            logger.warning("Libreria de Google Cloud BigQuery no instalada")
            return 0
        except Exception as e:
            logger.error(f"Error cargando a BigQuery: {e}")
            return 0


# Funcion de conveniencia para uso independiente
async def load_data(
    scores: List[ZoneSafetyScore],
    zones_gdf=None,
    job_id: Optional[str] = None
) -> int:
    """
    Cargar todos los datos a PostgreSQL y opcionalmente BigQuery

    Args:
        scores: Lista de objetos ZoneSafetyScore
        zones_gdf: GeoDataFrame opcional con zonas
        job_id: ID opcional del trabajo para rastreo

    Returns:
        Numero de registros cargados
    """
    async with DataLoader() as loader:
        # Cargar zonas si se proporcionan
        if zones_gdf is not None:
            await loader.load_zones(zones_gdf)

        # Cargar puntajes de seguridad
        records = await loader.load_zone_safety_scores(scores, job_id)

        # Tambien cargar a BigQuery si esta configurado
        if settings.is_gcp_enabled:
            await loader.load_to_bigquery(scores)

        return records