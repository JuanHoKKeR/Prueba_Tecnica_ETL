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
import zipfile
import tempfile
import os
import socket
import sys
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config.settings import settings
from ..models.schemas import CrimeIncident, TimeRange

logger = logging.getLogger(__name__)


def log_network_error(error: Exception, url: str, operation: str, client_info: dict = None):
    """
    Función para logging detallado de errores de red
    """
    error_details = {
        "operation": operation,
        "url": url,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "python_version": sys.version,
        "environment": os.getenv("ENVIRONMENT", "unknown")
    }
    
    # Información del cliente HTTP si está disponible
    if client_info:
        error_details.update(client_info)
    
    # Detalles específicos según el tipo de error
    if isinstance(error, httpx.HTTPStatusError):
        error_details.update({
            "status_code": error.response.status_code,
            "response_headers": dict(error.response.headers),
            "response_text": error.response.text[:500] if hasattr(error.response, 'text') else None,
            "request_url": str(error.request.url),
            "request_method": error.request.method,
            "request_headers": dict(error.request.headers)
        })
    elif isinstance(error, httpx.TimeoutException):
        error_details.update({
            "timeout_type": "HTTP timeout",
            "timeout_details": str(error)
        })
    elif isinstance(error, httpx.ConnectTimeout):
        error_details.update({
            "timeout_type": "Connection timeout",
            "connection_details": str(error)
        })
    elif isinstance(error, httpx.ReadTimeout):
        error_details.update({
            "timeout_type": "Read timeout",
            "read_details": str(error)
        })
    elif isinstance(error, httpx.ConnectError):
        error_details.update({
            "connection_error": str(error),
            "connection_type": "HTTP connection failed"
        })
    elif isinstance(error, (socket.gaierror, socket.timeout)):
        error_details.update({
            "network_error": str(error),
            "network_type": "DNS/Socket error"
        })
    
    # DNS resolution test
    try:
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname
        if hostname:
            import socket
            ip = socket.gethostbyname(hostname)
            error_details["dns_resolution"] = {"hostname": hostname, "resolved_ip": ip}
    except Exception as dns_error:
        error_details["dns_resolution"] = {"error": str(dns_error)}
    
    # Log detallado
    logger.error(f"Network error in {operation}:")
    logger.error(f"Error details: {json.dumps(error_details, indent=2, default=str)}")
    
    return error_details


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
            # Usar fechas más realistas - últimos 90 días de 2024
            start_date = datetime(2024, 10, 1)  # Octubre 2024
        if not end_date:
            end_date = datetime(2024, 12, 31)  # Diciembre 2024

        # Formatear fechas para la API (solo fecha, sin hora)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        url = f"{settings.datos_gov_api_base}/{settings.crime_api_endpoint}"

        # Construir parametros de consulta (obtener datos generales de hurtos)
        params = {
            "$limit": min(limit, 100),  # Limitar para pruebas
            "$order": "fecha_hecho DESC",
            "$select": "fecha_hecho,tipo_de_hurto,armas_medios,cantidad,departamento,municipio"
        }

        logger.info(f"Obteniendo datos de crimenes desde {start_str} hasta {end_str}")

        try:
            response = await self.http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            logger.info(f"Obtenidos {len(data)} registros de crimenes")
            if data:
                logger.info(f"Ejemplo de registro: {data[0]}")

            # Procesar y limpiar los datos
            processed_data = []
            for record in data:
                if record.get('fecha_hecho'):
                    processed_record = {
                        'incident_date': record['fecha_hecho'],
                        'incident_type': 'THEFT',
                        'modalidad': record.get('tipo_de_hurto', ''),
                        'barrio': '',  # No disponible en este dataset
                        'zona': '',    # No disponible en este dataset
                        'cantidad': int(record.get('cantidad', 1))
                    }
                    processed_data.append(processed_record)

            return processed_data

        except httpx.HTTPStatusError as e:
            client_info = {
                "client_timeout": "default",
                "params": params,
                "data_fetched": len(data) if 'data' in locals() else 0
            }
            log_network_error(e, url, "fetch_crime_data", client_info)
            logger.warning("Retornando lista vacía debido a error en API de crimenes")
            return []
        except Exception as e:
            client_info = {
                "client_timeout": "default",
                "params": params,
                "error_location": "fetch_crime_data general exception"
            }
            log_network_error(e, url, "fetch_crime_data", client_info)
            logger.warning("Retornando lista vacía debido a error en API de crimenes")
            return []

    async def fetch_crime_data_geojson(self, use_cache: bool = True) -> bool:
        """
        Descargar y extraer datos de criminalidad real de Bogotá desde ZIP
        
        Returns:
            bool: True si los datos se descargaron/extrajeron exitosamente
        """
        target_file = "DAILoc.geojson"
        
        # Si el archivo ya existe y no se fuerza refresh, usar cache
        if os.path.exists(target_file) and use_cache:
            logger.info(f"Usando archivo cacheado: {target_file}")
            return True
            
        try:
            logger.info("Descargando datos de criminalidad de Bogotá...")
            url = "https://datosabiertos.bogota.gov.co/dataset/7b270013-42ca-436b-9c1e-3bcb7d280c6b/resource/b24e6cfa-ae5d-465c-8fe7-e494cd377897/download/dai_gpkg.zip"
            
            # Descargar archivo ZIP
            response = await self.http_client.get(url)
            response.raise_for_status()
            
            # Crear archivo temporal para el ZIP
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_zip:
                tmp_zip.write(response.content)
                tmp_zip_path = tmp_zip.name
            
            # Extraer el archivo GPKG o GeoJSON del ZIP
            with zipfile.ZipFile(tmp_zip_path, 'r') as zip_ref:
                # Buscar archivo .gpkg o .geojson en el ZIP
                target_files = [f for f in zip_ref.namelist() if f.endswith(('.geojson', '.gpkg'))]
                if not target_files:
                    logger.error("No se encontró archivo .geojson ni .gpkg en el ZIP")
                    return False
                
                # Extraer el primer archivo encontrado
                source_file = target_files[0]
                zip_ref.extract(source_file, ".")
                
                # Si es GPKG, convertir a GeoJSON
                if source_file.endswith('.gpkg'):
                    logger.info(f"Convirtiendo {source_file} a GeoJSON...")
                    try:
                        # Leer GPKG y convertir a GeoJSON
                        gdf = gpd.read_file(source_file)
                        gdf.to_file(target_file, driver='GeoJSON')
                        # Limpiar archivo GPKG temporal
                        os.unlink(source_file)
                        logger.info(f"Conversión exitosa: {source_file} -> {target_file}")
                    except Exception as e:
                        logger.error(f"Error convirtiendo GPKG a GeoJSON: {e}")
                        return False
                else:
                    # Renombrar GeoJSON si es necesario
                    if source_file != target_file:
                        os.rename(source_file, target_file)
            
            # Limpiar archivo temporal
            os.unlink(tmp_zip_path)
            
            logger.info(f"Datos de criminalidad descargados exitosamente: {target_file}")
            return True
            
        except Exception as e:
            log_network_error(e, url, "fetch_crime_data_geojson", 
                            {"operation": "download_and_extract_zip", "target_file": target_file})
            return False

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
            log_network_error(e, settings.bike_lanes_geojson_url, "fetch_bike_lanes", {"cache_file": str(cache_file)})
            # Intentar usar datos cacheados aunque expirados
            if cache_file.exists():
                logger.warning("Usando cache expirado debido a error de obtencion")
                return gpd.read_file(cache_file)
            logger.warning("Retornando GeoDataFrame vacío debido a error en API de ciclorutas")
            return gpd.GeoDataFrame()

    async def fetch_bike_parking(self, use_cache: bool = True) -> pd.DataFrame:
        """
        Obtener datos de estacionamientos de bicis

        Args:
            use_cache: Si usar datos cacheados si estan disponibles

        Returns:
            DataFrame con ubicaciones de estacionamientos
        """
        cache_file = self.cache_dir / "bike_parking.geojson"

        # Revisar cache primero
        if use_cache and cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age.total_seconds() < settings.cache_ttl_seconds:
                logger.info("Usando datos cacheados de estacionamientos")
                gdf = gpd.read_file(cache_file)
                return pd.DataFrame(gdf.drop(columns='geometry'))

        logger.info("Obteniendo datos de estacionamientos de la fuente")

        try:
            response = await self.http_client.get(settings.parking_csv_url)
            response.raise_for_status()

            # Guardar en cache
            cache_file.write_bytes(response.content)

            # Cargar como GeoDataFrame y convertir a DataFrame
            gdf = gpd.read_file(cache_file)
            df = pd.DataFrame(gdf.drop(columns='geometry'))

            # Limpiar nombres de columnas
            df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')

            logger.info(f"Obtenidos {len(df)} ubicaciones de estacionamientos")
            return df

        except Exception as e:
            log_network_error(e, settings.parking_csv_url, "fetch_bike_parking", {"cache_file": str(cache_file)})
            # Intentar usar datos cacheados aunque expirados
            if cache_file.exists():
                logger.warning("Usando cache expirado debido a error de obtencion")
                gdf = gpd.read_file(cache_file)
                return pd.DataFrame(gdf.drop(columns='geometry'))
            logger.warning("Retornando DataFrame vacío debido a error en API de estacionamientos")
            return pd.DataFrame()

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
            log_network_error(e, url, f"fetch_zones_{zone_type}", 
                            {"zone_type": zone_type, "cache_file": str(cache_file)})
            # Intentar usar datos cacheados aunque expirados
            if cache_file.exists():
                logger.warning("Usando cache expirado debido a error de obtencion")
                return gpd.read_file(cache_file)
            logger.warning(f"Retornando GeoDataFrame vacío debido a error en API de {zone_type}")
            return gpd.GeoDataFrame()

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

        # Primero descargar datos de criminalidad real (archivo grande)
        await self.fetch_crime_data_geojson(use_cache)

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