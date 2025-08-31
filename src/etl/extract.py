"""
Modulo para extraccion de datos de varias fuentes
"""

import httpx
import pandas as pd
import geopandas as gpd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging
from pathlib import Path
import json
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config.settings import settings
from ..models.schemas import CrimeIncident, TimeRange

logger = logging.getLogger(__name__)


class DataExtractor:
    """Clase para manejar extraccion de datos de varias fuentes"""

    def __init__(self):
        self.cache_dir = settings.data_cache_dir  # Directorio para cache de datos
        self.http_client = None  # Cliente HTTP para requests

    async def __aenter__(self):
        """Entrada al context manager async"""
        self.http_client = httpx.AsyncClient(timeout=settings.request_timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Salida del context manager async"""
        if self.http_client:
            await self.http_client.aclose()

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def fetch_crime_data(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10000
    ) -> List[Dict[str, Any]]:
        """
        Obtener datos de crimenes de la API de datos.gov.co

        Args:
            start_date: Fecha de inicio para obtener datos
            end_date: Fecha de fin para obtener datos
            limit: Maximo numero de registros a obtener

        Returns:
            Lista de diccionarios con incidentes de crimen
        """
        if not start_date:
            start_date = datetime.now() - timedelta(days=90)  # Por defecto ultimos 90 dias
        if not end_date:
            end_date = datetime.now()

        # Formatear fechas para la API
        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%S")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%S")

        url = f"{settings.datos_gov_api_base}/{settings.crime_api_endpoint}"

        # Construir parametros de consulta
        params = {
            "$where": (
                f"departamento='CUNDINAMARCA' AND "
                f"municipio='BOGOTÁ D.C.(CT)' AND "
                f"modalidad IN ('HURTO MOTOCICLETAS', 'HURTO BICICLETAS') AND "
                f"fecha between '{start_str}' and '{end_str}'"
            ),
            "$limit": limit,
            "$order": "fecha DESC",
            "$select": "fecha,modalidad,barrio,zona,cantidad,arma_empleada"
        }

        logger.info(f"Obteniendo datos de crimenes desde {start_str} hasta {end_str}")

        try:
            response = await self.http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            logger.info(f"Obtenidos {len(data)} registros de crimenes")

            # Procesar y limpiar los datos
            processed_data = []
            for record in data:
                if record.get('fecha'):
                    processed_record = {
                        'incident_date': record['fecha'],
                        'incident_type': 'THEFT',
                        'modalidad': record.get('modalidad', ''),
                        'barrio': record.get('barrio', ''),
                        'zona': record.get('zona', ''),
                        'cantidad': int(record.get('cantidad', 1))
                    }
                    processed_data.append(processed_record)

            return processed_data

        except httpx.HTTPStatusError as e:
            logger.error(f"Error HTTP obteniendo datos de crimenes: {e}")
            raise
        except Exception as e:
            logger.error(f"Error obteniendo datos de crimenes: {e}")
            raise

    async def fetch_bike_lanes(self, use_cache: bool = True) -> gpd.GeoDataFrame:
        """
        Obtener datos de ciclorutas

        Args:
            use_cache: Si usar datos cacheados si estan disponibles

        Returns:
            GeoDataFrame con ciclorutas
        """
        cache_file = self.cache_dir / "bike_lanes.geojson"

        # Revisar cache primero
        if use_cache and cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age.total_seconds() < settings.cache_ttl_seconds:
                logger.info("Usando datos cacheados de ciclorutas")
                return gpd.read_file(cache_file)

        logger.info("Obteniendo datos de ciclorutas de la fuente")

        try:
            response = await self.http_client.get(settings.bike_lanes_geojson_url)
            response.raise_for_status()

            # Guardar en cache
            cache_file.write_bytes(response.content)

            # Cargar como GeoDataFrame
            gdf = gpd.read_file(cache_file)

            # Calcular longitudes si no estan presentes
            if 'length_km' not in gdf.columns:
                # Convertir a CRS apropiado para calculo de distancias (Colombia)
                gdf_projected = gdf.to_crs('EPSG:3116')
                gdf['length_km'] = gdf_projected.geometry.length / 1000

            logger.info(f"Obtenidos {len(gdf)} segmentos de ciclorutas")
            return gdf

        except Exception as e:
            logger.error(f"Error obteniendo ciclorutas: {e}")
            # Intentar usar datos cacheados aunque expirados
            if cache_file.exists():
                logger.warning("Usando cache expirado debido a error de obtencion")
                return gpd.read_file(cache_file)
            raise

    async def fetch_bike_parking(self, use_cache: bool = True) -> pd.DataFrame:
        """
        Obtener datos de estacionamientos de bicis

        Args:
            use_cache: Si usar datos cacheados si estan disponibles

        Returns:
            DataFrame con ubicaciones de estacionamientos
        """
        cache_file = self.cache_dir / "bike_parking.csv"

        # Revisar cache primero
        if use_cache and cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age.total_seconds() < settings.cache_ttl_seconds:
                logger.info("Usando datos cacheados de estacionamientos")
                return pd.read_csv(cache_file)

        logger.info("Obteniendo datos de estacionamientos de la fuente")

        try:
            response = await self.http_client.get(settings.parking_csv_url)
            response.raise_for_status()

            # Guardar en cache
            cache_file.write_bytes(response.content)

            # Cargar como DataFrame
            df = pd.read_csv(cache_file)

            # Limpiar nombres de columnas
            df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')

            logger.info(f"Obtenidos {len(df)} ubicaciones de estacionamientos")
            return df

        except Exception as e:
            logger.error(f"Error obteniendo estacionamientos: {e}")
            # Intentar usar datos cacheados aunque expirados
            if cache_file.exists():
                logger.warning("Usando cache expirado debido a error de obtencion")
                return pd.read_csv(cache_file)
            raise

    async def fetch_zones(self, zone_type: str = "localidades", use_cache: bool = True) -> gpd.GeoDataFrame:
        """
        Obtener limites de zonas (localidades o UPZ)

        Args:
            zone_type: Tipo de zonas a obtener ('localidades' o 'upz')
            use_cache: Si usar datos cacheados si estan disponibles

        Returns:
            GeoDataFrame con limites de zonas
        """
        if zone_type == "localidades":
            url = settings.localidades_geojson_url
            cache_file = self.cache_dir / "localidades.geojson"
        elif zone_type == "upz":
            url = settings.upz_geojson_url
            cache_file = self.cache_dir / "upz.geojson"
        else:
            raise ValueError(f"Tipo de zona invalido: {zone_type}")

        # Revisar cache primero
        if use_cache and cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age.total_seconds() < settings.cache_ttl_seconds:
                logger.info(f"Usando datos cacheados de {zone_type}")
                return gpd.read_file(cache_file)

        logger.info(f"Obteniendo datos de {zone_type} de la fuente")

        try:
            response = await self.http_client.get(url)
            response.raise_for_status()

            # Guardar en cache
            cache_file.write_bytes(response.content)

            # Cargar como GeoDataFrame
            gdf = gpd.read_file(cache_file)

            # Calcular area si no esta presente
            if 'area_km2' not in gdf.columns:
                # Convertir a CRS apropiado para calculo de areas (Colombia)
                gdf_projected = gdf.to_crs('EPSG:3116')
                gdf['area_km2'] = gdf_projected.geometry.area / 1_000_000

            logger.info(f"Obtenidos {len(gdf)} {zone_type}")
            return gdf

        except Exception as e:
            logger.error(f"Error obteniendo {zone_type}: {e}")
            # Intentar usar datos cacheados aunque expirados
            if cache_file.exists():
                logger.warning("Usando cache expirado debido a error de obtencion")
                return gpd.read_file(cache_file)
            raise

    async def fetch_all_data(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Obtener todos los datos requeridos de las fuentes

        Args:
            start_date: Fecha de inicio para datos de crimenes
            end_date: Fecha de fin para datos de crimenes
            use_cache: Si usar datos cacheados para fuentes estaticas

        Returns:
            Diccionario con todos los datos obtenidos
        """
        logger.info("Iniciando obtencion paralela de datos de todas las fuentes")

        # Ejecutar todas las obtenciones en paralelo
        tasks = [
            self.fetch_crime_data(start_date, end_date),
            self.fetch_bike_lanes(use_cache),
            self.fetch_bike_parking(use_cache),
            self.fetch_zones("localidades", use_cache),
            self.fetch_zones("upz", use_cache)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Revisar errores
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error en tarea {i}: {result}")
                raise result

        crime_data, bike_lanes, bike_parking, localidades, upz = results

        return {
            'crime_data': crime_data,
            'bike_lanes': bike_lanes,
            'bike_parking': bike_parking,
            'localidades': localidades,
            'upz': upz
        }


# Funcion de conveniencia para uso independiente
async def extract_data(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Extraer todos los datos de las fuentes

    Args:
        start_date: Fecha de inicio para datos de crimenes
        end_date: Fecha de fin para datos de crimenes
        use_cache: Si usar datos cacheados

    Returns:
        Diccionario con todos los datos extraidos
    """
    async with DataExtractor() as extractor:
        return await extractor.fetch_all_data(start_date, end_date, use_cache)