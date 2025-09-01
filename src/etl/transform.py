"""
Modulo para transformacion de datos y analisis de seguridad de zonas
"""

import pandas as pd
import geopandas as gpd
import numpy as np
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Tuple
from shapely.geometry import Point
import logging
import requests
import os

from ..config.settings import settings
from ..models.schemas import (
    RiskLevel, TrendDirection, SafetyMetrics,
    SafetyRecommendations, ZoneSafetyScore
)

logger = logging.getLogger(__name__)


def load_real_crime_data() -> gpd.GeoDataFrame:
    """
    Cargar datos reales de criminalidad de Bogotá desde el archivo local
    
    Returns:
        GeoDataFrame con datos de criminalidad por localidad
    """
    # Buscar el archivo en el directorio actual y en cache
    possible_paths = [
        "DAILoc.geojson",  # Directorio actual
        os.path.join(os.getcwd(), "DAILoc.geojson"),  # Directorio de trabajo
        os.path.join("/tmp/roda_cache", "DAILoc.geojson"),  # Cache
    ]
    
    crime_file_path = None
    for path in possible_paths:
        if os.path.exists(path):
            crime_file_path = path
            break
    
    if not crime_file_path:
        logger.error(f"Archivo de datos de criminalidad no encontrado en: {possible_paths}")
        raise FileNotFoundError(f"Archivo de criminalidad no encontrado en ninguna de las rutas: {possible_paths}")
    
    try:
        crime_gdf = gpd.read_file(crime_file_path)
        logger.info(f"Cargados datos de criminalidad desde {crime_file_path}: {len(crime_gdf)} localidades")
        return crime_gdf
    except Exception as e:
        logger.error(f"Error cargando datos de criminalidad desde {crime_file_path}: {e}")
        raise


def normalize_locality_name(name: str) -> str:
    """
    Normalizar nombres de localidades para matching
    
    Args:
        name: Nombre original de la localidad
        
    Returns:
        Nombre normalizado
    """
    # Mapeo de nombres con acentos/diferencias
    name_mapping = {
        'LOS MARTIRES': 'LOS MÁRTIRES',
        'USAQUEN': 'USAQUÉN', 
        'SAN CRISTOBAL': 'SAN CRISTÓBAL',
        'CIUDAD BOLIVAR': 'CIUDAD BOLÍVAR',
        'FONTIBON': 'FONTIBÓN',
        'ENGATIVA': 'ENGATIVÁ'
    }
    
    normalized = name.upper().strip()
    return name_mapping.get(normalized, normalized)


class DataTransformer:
    """Clase para manejar transformacion de datos y calculo de puntajes de seguridad"""

    def __init__(self):
        self.risk_thresholds = settings.risk_thresholds  # Umbrales de riesgo desde settings
        self.crime_weights = {
            'CMH25CONT': 10.0,    # Homicidios - peso máximo
            'CMDS25CONT': 8.0,    # Delitos sexuales - muy alto
            'CMHA25CONT': 6.0,    # Hurto automotores - alto
            'CMHM25CONT': 5.0,    # Hurto motocicletas - alto
            'CMHR25CONT': 4.0,    # Hurto residencias - medio-alto
            'CMHP25CONT': 3.0,    # Hurto personas - medio
            'CMHC25CONT': 3.0,    # Hurto comercio - medio
            'CMHB25CONT': 2.0,    # Hurto bicicletas - medio-bajo
            'CMHCE25CON': 2.0,    # Hurto celulares - medio-bajo
            'CMLP25CONT': 4.0,    # Lesiones personales - medio-alto
            'CMVI25CONT': 3.0,    # Violencia intrafamiliar - medio
        }

    def process_crime_data(self, crime_data: List[Dict]) -> pd.DataFrame:
        """
        Procesar datos crudos de crimenes en un DataFrame estructurado

        Args:
            crime_data: Lista de diccionarios con incidentes de crimen

        Returns:
            DataFrame procesado con incidentes de crimen
        """
        if not crime_data:
            logger.warning("No hay datos de crimenes para procesar")
            return pd.DataFrame()

        df = pd.DataFrame(crime_data)

        # Convertir strings de fecha a datetime (formato DD/MM/YYYY)
        df['incident_date'] = pd.to_datetime(df['incident_date'], format='%d/%m/%Y', errors='coerce')

        # Limpiar y estandarizar campos de texto
        text_cols = ['modalidad', 'barrio', 'zona']
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].str.strip().str.upper()

        # Expandir registros basados en 'cantidad' si esta presente
        if 'cantidad' in df.columns:
            df = df.loc[df.index.repeat(df['cantidad'])].reset_index(drop=True)

        logger.info(f"Procesados {len(df)} incidentes de crimen")
        return df

    def spatial_join_crimes_to_zones(
        self,
        crimes_df: pd.DataFrame,
        zones_gdf: gpd.GeoDataFrame
    ) -> pd.DataFrame:
        """
        Unir espacialmente incidentes de crimen a zonas

        Args:
            crimes_df: DataFrame con incidentes de crimen
            zones_gdf: GeoDataFrame con limites de zonas

        Returns:
            DataFrame con asignaciones de zona
        """
        # Por ahora, uniremos basado en matching de texto de barrio/localidad
        # En implementacion completa, usariamos lat/lon para union espacial

        if 'barrio' in crimes_df.columns:
            # Intentar matchear barrios a zonas
            # Esto es simplificado - en produccion, tendrias un mapping apropiado
            crimes_df['zone_match'] = crimes_df['barrio']

        return crimes_df

    def calculate_zone_metrics_real_data(
        self,
        zone_name: str,
        crime_gdf: gpd.GeoDataFrame,
        bike_lanes_gdf: gpd.GeoDataFrame,
        parking_df: pd.DataFrame,
        calculation_date: datetime = None
    ) -> SafetyMetrics:
        """
        Calcular métricas de seguridad usando datos reales de criminalidad

        Args:
            zone_name: Nombre de la localidad
            crime_gdf: GeoDataFrame con datos reales de criminalidad
            bike_lanes_gdf: GeoDataFrame con ciclorutas
            parking_df: DataFrame con ubicaciones de estacionamientos
            calculation_date: Fecha para cálculo (por defecto: hoy)

        Returns:
            Objeto SafetyMetrics con valores calculados
        """
        if calculation_date is None:
            calculation_date = datetime.now()

        # Buscar datos de la localidad en el dataset de criminalidad
        normalized_zone_name = normalize_locality_name(zone_name)
        zone_crime_data = crime_gdf[crime_gdf['CMNOMLOCAL'].str.upper() == normalized_zone_name.upper()]
        
        if zone_crime_data.empty:
            logger.warning(f"No se encontraron datos de criminalidad para {zone_name} (normalizado: {normalized_zone_name})")
            # Retornar métricas por defecto para zonas sin datos
            return SafetyMetrics(
                thefts_last_7_days=0,
                thefts_last_30_days=0,
                thefts_last_90_days=0,
                theft_density_per_km2=0.0,
                bike_lane_coverage_km=bike_lanes_km,
                safe_parking_spots=parking_spots,
                parking_density_per_km2=round(parking_spots / 1.0, 2),  # Usar 1 km² por defecto
                bike_lane_density_per_km2=round(bike_lanes_km / 1.0, 2)
            )

        zone_data = zone_crime_data.iloc[0]
        
        # Calcular métricas de criminalidad usando los pesos definidos
        weighted_crime_score = 0.0
        total_crimes = 0
        violent_crimes = 0
        property_crimes = 0
        
        # Categorizar y ponderar delitos
        violent_crime_cols = ['CMH25CONT', 'CMDS25CONT', 'CMLP25CONT', 'CMVI25CONT']
        property_crime_cols = ['CMHA25CONT', 'CMHM25CONT', 'CMHR25CONT', 'CMHP25CONT', 
                              'CMHC25CONT', 'CMHB25CONT', 'CMHCE25CON']
        
        for col, weight in self.crime_weights.items():
            if col in zone_data and pd.notna(zone_data[col]):
                crime_count = float(zone_data[col])
                weighted_crime_score += crime_count * weight
                total_crimes += crime_count
                
                if col in violent_crime_cols:
                    violent_crimes += crime_count
                elif col in property_crime_cols:
                    property_crimes += crime_count

        # Los datos de 2025 son de enero-junio (6 meses), necesitamos escalar
        # para obtener estimaciones realistas por período
        months_in_data = 6  # Enero a junio 2025
        
        # Calcular métricas escaladas temporalmente
        total_crimes_monthly = total_crimes / months_in_data
        property_crimes_monthly = property_crimes / months_in_data
        
        # Estimar para diferentes períodos
        thefts_7_days = int(property_crimes_monthly * (7/30))  # 7 días de un mes
        thefts_30_days = int(property_crimes_monthly)  # 1 mes
        thefts_90_days = int(property_crimes_monthly * 3)  # 3 meses

        # Calcular área de la zona en km² (usar SHAPE_AREA que ya está en grados cuadrados)
        # Convertir grados cuadrados a km² aproximadamente
        zone_area_degrees = zone_data.get('SHAPE_AREA', 0.01)
        # En Colombia, 1 grado ≈ 111 km, entonces 1 grado² ≈ 12,321 km²
        zone_area_km2 = zone_area_degrees * 12321
        
        # Si el área calculada es irreal, usar estimación basada en localidades típicas de Bogotá
        if zone_area_km2 < 1 or zone_area_km2 > 1000:  
            zone_area_km2 = 50.0  # Aproximado 50 km² por localidad en Bogotá

        # Calcular densidad de robos por km² (robos mensuales por km²)
        theft_density_per_km2 = property_crimes_monthly / zone_area_km2

        # Calcular infraestructura de apoyo
        bike_lanes_km = self._calculate_bike_lanes_in_zone(zone_name, bike_lanes_gdf)
        parking_spots = self._calculate_parking_in_zone(zone_name, parking_df)

        return SafetyMetrics(
            thefts_last_7_days=thefts_7_days,
            thefts_last_30_days=thefts_30_days,
            thefts_last_90_days=thefts_90_days,
            theft_density_per_km2=round(theft_density_per_km2, 2),
            bike_lane_coverage_km=bike_lanes_km,
            safe_parking_spots=parking_spots,
            parking_density_per_km2=round(parking_spots / zone_area_km2, 2),
            bike_lane_density_per_km2=round(bike_lanes_km / zone_area_km2, 2)
        )

    def _calculate_bike_lanes_in_zone(self, zone_name: str, bike_lanes_gdf: gpd.GeoDataFrame) -> float:
        """
        Calcular kilómetros de ciclorrutas en una zona
        
        Args:
            zone_name: Nombre de la zona
            bike_lanes_gdf: GeoDataFrame con ciclorrutas
            
        Returns:
            Kilómetros de ciclorrutas en la zona
        """
        try:
            if bike_lanes_gdf.empty:
                return 0.0
            
            # Filtrar ciclorrutas por localidad (si tienen campo de localidad)
            zone_bike_lanes = bike_lanes_gdf[
                bike_lanes_gdf.get('localidad', '').str.upper() == zone_name.upper()
            ] if 'localidad' in bike_lanes_gdf.columns else pd.DataFrame()
            
            if zone_bike_lanes.empty:
                # Si no hay campo de localidad, usar una estimación basada en el total
                total_length = bike_lanes_gdf.get('length_km', bike_lanes_gdf.get('length', pd.Series([0]))).sum()
                return round(total_length / 20, 2)  # Distribuir entre 20 localidades
            
            # Calcular longitud total
            if 'length_km' in zone_bike_lanes.columns:
                return round(zone_bike_lanes['length_km'].sum(), 2)
            elif 'length' in zone_bike_lanes.columns:
                return round(zone_bike_lanes['length'].sum() / 1000, 2)  # Convertir metros a km
            else:
                return round(len(zone_bike_lanes) * 0.5, 2)  # Estimación 500m por segmento
                
        except Exception as e:
            logger.warning(f"Error calculando ciclorrutas para {zone_name}: {e}")
            return 0.0

    def _calculate_parking_in_zone(self, zone_name: str, parking_df: pd.DataFrame) -> int:
        """
        Calcular número de estacionamientos en una zona
        
        Args:
            zone_name: Nombre de la zona
            parking_df: DataFrame con estacionamientos
            
        Returns:
            Número de estacionamientos en la zona
        """
        try:
            if parking_df.empty:
                return 0
            
            # Filtrar estacionamientos por localidad
            zone_parking = parking_df[
                parking_df.get('localidad', '').str.upper() == zone_name.upper()
            ] if 'localidad' in parking_df.columns else pd.DataFrame()
            
            if zone_parking.empty:
                # Si no hay campo de localidad, usar estimación
                return max(1, len(parking_df) // 20)  # Distribuir entre 20 localidades
            
            # Sumar capacidades o contar ubicaciones
            if 'capacidad' in zone_parking.columns:
                return int(zone_parking['capacidad'].sum())
            else:
                return len(zone_parking)
                
        except Exception as e:
            logger.warning(f"Error calculando estacionamientos para {zone_name}: {e}")
            return 0

    def calculate_zone_metrics(
        self,
        zone_code: str,
        zone_gdf: gpd.GeoDataFrame,
        crimes_df: pd.DataFrame,
        bike_lanes_gdf: gpd.GeoDataFrame,
        parking_df: pd.DataFrame,
        calculation_date: datetime = None
    ) -> SafetyMetrics:
        """
        Calcular metricas de seguridad para una zona especifica (método legacy)

        Args:
            zone_code: Identificador de zona
            zone_gdf: GeoDataFrame con limites de zonas
            crimes_df: DataFrame con incidentes de crimen
            bike_lanes_gdf: GeoDataFrame con ciclorutas
            parking_df: DataFrame con ubicaciones de estacionamientos
            calculation_date: Fecha para calculo (por defecto: hoy)

        Returns:
            Objeto SafetyMetrics con valores calculados
        """
        if calculation_date is None:
            calculation_date = datetime.now()

        # Obtener geometria y area de la zona
        zone = zone_gdf[zone_gdf['LocNombre'] == zone_code]
        if zone.empty:
            logger.warning(f"Zona {zone_code} no encontrada")
            return SafetyMetrics()

        zone_geom = zone.geometry.iloc[0]
        zone_area = zone['area_km2'].iloc[0] if 'area_km2' in zone.columns else 1.0

        # Calcular metricas de crimen
        recent_crimes = crimes_df[
            crimes_df['incident_date'] > calculation_date - timedelta(days=90)
        ]

        # Filtrar crimenes por zona (simplificado - deberia usar union espacial)
        zone_crimes_filters = []
        if 'barrio' in recent_crimes.columns:
            zone_crimes_filters.append(recent_crimes['barrio'].str.contains(zone_code, na=False))
        if 'zona' in recent_crimes.columns:
            zone_crimes_filters.append(recent_crimes['zona'].str.contains(zone_code, na=False))
        
        if zone_crimes_filters:
            zone_crimes = recent_crimes[
                zone_crimes_filters[0] if len(zone_crimes_filters) == 1 
                else zone_crimes_filters[0] | zone_crimes_filters[1]
            ]
        else:
            zone_crimes = pd.DataFrame()

        thefts_7d = len(zone_crimes[
            zone_crimes['incident_date'] > calculation_date - timedelta(days=7)
        ])
        thefts_30d = len(zone_crimes[
            zone_crimes['incident_date'] > calculation_date - timedelta(days=30)
        ])
        thefts_90d = len(zone_crimes)

        theft_density = thefts_30d / zone_area if zone_area > 0 else 0

        # Calcular metricas de ciclorutas
        # Interseccion espacial con zona
        zone_lanes = bike_lanes_gdf[
            bike_lanes_gdf.geometry.intersects(zone_geom)
        ]

        # Usar SHAPE_Length de la fuente, convertir a km (asumiendo que está en metros)
        if not zone_lanes.empty and 'SHAPE_Length' in zone_lanes.columns:
            bike_lane_km = zone_lanes['SHAPE_Length'].sum() / 1000  # Convertir metros a km
        else:
            bike_lane_km = 0
        
        bike_lane_density = bike_lane_km / zone_area if zone_area > 0 else 0

        # Calcular metricas de estacionamientos
        # Por simplicidad, contar todos los estacionamientos en el nombre de zona
        if 'localidad' in parking_df.columns:
            zone_parking = parking_df[
                parking_df['localidad'].str.contains(zone_code, na=False)
            ]
        else:
            zone_parking = pd.DataFrame()  # DataFrame vacío si no hay columna localidad

        parking_spots = len(zone_parking)
        parking_density = parking_spots / zone_area if zone_area > 0 else 0

        return SafetyMetrics(
            thefts_last_7_days=thefts_7d,
            thefts_last_30_days=thefts_30d,
            thefts_last_90_days=thefts_90d,
            theft_density_per_km2=round(theft_density, 3),
            bike_lane_coverage_km=round(bike_lane_km, 2),
            bike_lane_density_per_km2=round(bike_lane_density, 3),
            safe_parking_spots=parking_spots,
            parking_density_per_km2=round(parking_density, 3)
        )

    def calculate_safety_score(self, metrics: SafetyMetrics) -> Tuple[float, RiskLevel]:
        """
        Calcular puntaje de seguridad desde metricas

        Args:
            metrics: Objeto SafetyMetrics

        Returns:
            Tupla de (puntaje_seguridad, nivel_riesgo)
        """
        # Puntaje base de 100
        score = 100.0

        # Penalizar por robos recientes (últimos 7 días tienen más peso)
        recent_theft_penalty = min(metrics.thefts_last_7_days * 0.1, 20)  # Max -20 puntos
        score -= recent_theft_penalty

        # Penalizar por robos en el último mes (escalado según cantidad)
        if metrics.thefts_last_30_days > 2000:
            monthly_theft_penalty = 40  # Zonas muy peligrosas
        elif metrics.thefts_last_30_days > 1500:
            monthly_theft_penalty = 35
        elif metrics.thefts_last_30_days > 1000:
            monthly_theft_penalty = 30
        elif metrics.thefts_last_30_days > 500:
            monthly_theft_penalty = 20
        elif metrics.thefts_last_30_days > 100:
            monthly_theft_penalty = 10
        else:
            monthly_theft_penalty = 0
        
        score -= monthly_theft_penalty

        # Penalizar por densidad de robos por km² (max -15 puntos)
        if metrics.theft_density_per_km2 > 50:
            density_penalty = 15  # Muy alta densidad
        elif metrics.theft_density_per_km2 > 30:
            density_penalty = 12
        elif metrics.theft_density_per_km2 > 20:
            density_penalty = 10
        elif metrics.theft_density_per_km2 > 10:
            density_penalty = 6
        elif metrics.theft_density_per_km2 > 5:
            density_penalty = 3
        else:
            density_penalty = 0
            
        score -= density_penalty

        # Recompensar por infraestructura de estacionamientos (max +10 puntos)
        parking_bonus = min(metrics.parking_density_per_km2 * 5, 10)
        score += parking_bonus

        # Recompensar por infraestructura de ciclorutas (max +15 puntos)
        bikelane_bonus = min(metrics.bike_lane_density_per_km2 * 10, 15)
        score += bikelane_bonus

        # Asegurar que el puntaje este entre 0 y 100
        score = max(0, min(100, score))

        # Determinar nivel de riesgo
        risk_level = self.get_risk_level(score)

        return round(score, 2), risk_level

    def get_risk_level(self, score: float) -> RiskLevel:
        """
        Determinar nivel de riesgo desde puntaje de seguridad

        Args:
            score: Puntaje de seguridad (0-100)

        Returns:
            Valor enum RiskLevel
        """
        for level, (min_score, max_score) in self.risk_thresholds.items():
            if min_score <= score < max_score:
                return RiskLevel(level)
        return RiskLevel.MEDIUM

    def calculate_trend(
        self,
        current_metrics: SafetyMetrics,
        previous_metrics: Optional[SafetyMetrics] = None
    ) -> Tuple[TrendDirection, float]:
        """
        Calcular direccion de tendencia y porcentaje

        Args:
            current_metrics: Metricas del periodo actual
            previous_metrics: Metricas del periodo anterior

        Returns:
            Tupla de (direccion_tendencia, porcentaje_tendencia)
        """
        if not previous_metrics:
            return TrendDirection.STABLE, 0.0

        # Comparar conteos de robos de 30 dias
        current_thefts = current_metrics.thefts_last_30_days
        previous_thefts = previous_metrics.thefts_last_30_days

        if previous_thefts == 0:
            if current_thefts == 0:
                return TrendDirection.STABLE, 0.0
            else:
                return TrendDirection.WORSENING, 100.0

        change_pct = ((current_thefts - previous_thefts) / previous_thefts) * 100

        if change_pct < -10:
            trend = TrendDirection.IMPROVING
        elif change_pct > 10:
            trend = TrendDirection.WORSENING
        else:
            trend = TrendDirection.STABLE

        return trend, round(change_pct, 2)

    def generate_recommendations(
        self,
        zone_code: str,
        metrics: SafetyMetrics,
        risk_level: RiskLevel,
        bike_lanes_gdf: gpd.GeoDataFrame,
        parking_df: pd.DataFrame
    ) -> SafetyRecommendations:
        """
        Generar recomendaciones de seguridad personalizadas para una zona

        Args:
            zone_code: Identificador de zona
            metrics: Metricas de seguridad de zona
            risk_level: Nivel de riesgo calculado
            bike_lanes_gdf: GeoDataFrame con ciclorutas
            parking_df: DataFrame con ubicaciones de estacionamientos

        Returns:
            Objeto SafetyRecommendations personalizado
        """
        recommendations = SafetyRecommendations()

        # Recomendaciones de horarios basadas en nivel de riesgo y criminalidad
        if risk_level == RiskLevel.VERY_LOW:
            recommendations.best_hours = [
                "5:00 AM - 10:00 PM (cualquier hora es segura)",
                "Especialmente recomendado 6:00 AM - 9:00 AM",
                "Horario vespertino 4:00 PM - 7:00 PM"
            ]
        elif risk_level == RiskLevel.LOW:
            recommendations.best_hours = [
                "6:00 AM - 9:00 AM (horas pico matutinas)",
                "12:00 PM - 2:00 PM (almuerzo)",
                "5:00 PM - 7:00 PM (regreso del trabajo)"
            ]
        elif risk_level == RiskLevel.MEDIUM:
            recommendations.best_hours = [
                "7:00 AM - 8:30 AM (máximo tráfico)",
                "12:00 PM - 1:30 PM (mayor vigilancia)",
                "Evitar después de 8:00 PM"
            ]
        else:  # HIGH o VERY_HIGH
            recommendations.best_hours = [
                "7:00 AM - 8:00 AM solamente",
                "12:00 PM - 1:00 PM con precaución",
                "NO recomendado después de 6:00 PM"
            ]

        # Áreas a evitar basadas en criminalidad
        if metrics.theft_density_per_km2 > 30:
            recommendations.avoid_areas = [
                f"Zona de alta criminalidad: {metrics.theft_density_per_km2:.1f} robos/km²/mes",
                "Evitar calles sin iluminación después de 7 PM",
                "No usar ciclorutas aisladas los fines de semana",
                "Evitar paradas prolongadas en semáforos"
            ]
        elif metrics.theft_density_per_km2 > 20:
            recommendations.avoid_areas = [
                "Calles con poca iluminación después de 8 PM",
                "Zonas industriales sin vigilancia",
                "Parques después del anochecer"
            ]
        elif metrics.theft_density_per_km2 > 10:
            recommendations.avoid_areas = [
                "Precaución en horarios nocturnos",
                "Evitar zonas muy solitarias"
            ]
        # Si es muy segura, no hay áreas específicas que evitar

        # Rutas seguras basadas en infraestructura y nivel de riesgo
        if metrics.bike_lane_coverage_km > 20:
            recommendations.safe_routes = [
                f"Excelente infraestructura: {metrics.bike_lane_coverage_km:.1f} km de ciclorutas",
                "Usar ciclorutas segregadas principales",
                "Corredores verdes y parques lineales",
                "Vías con semáforos sincronizados para ciclistas",
                "Rutas conectadas con TransMilenio"
            ]
        elif metrics.bike_lane_coverage_km > 10:
            recommendations.safe_routes = [
                f"Buena infraestructura: {metrics.bike_lane_coverage_km:.1f} km disponibles",
                "Priorizar ciclorutas existentes",
                "Avenidas principales con carril exclusivo",
                "Evitar calles secundarias sin infraestructura"
            ]
        elif metrics.bike_lane_coverage_km > 5:
            recommendations.safe_routes = [
                f"Infraestructura limitada: {metrics.bike_lane_coverage_km:.1f} km",
                "Usar con precaución las ciclorutas disponibles",
                "Calles con menos tráfico vehicular",
                "Vías con berma amplia y buena visibilidad"
            ]
        else:
            recommendations.safe_routes = [
                "Infraestructura ciclista muy limitada",
                "Calles residenciales con bajo flujo vehicular",
                "Vías secundarias con buena visibilidad",
                "Considerar transporte alternativo en horas pico"
            ]

        # Información de estacionamientos basada en disponibilidad
        if metrics.safe_parking_spots > 15:
            recommendations.parking_locations = [
                {
                    "name": f"Estacionamientos seguros en {zone_code}",
                    "address": "Ubicaciones distribuidas en la localidad", 
                    "security_level": "HIGH" if risk_level in [RiskLevel.VERY_LOW, RiskLevel.LOW] else "MEDIUM",
                    "capacity": metrics.safe_parking_spots,
                    "recommendation": "Buena disponibilidad de estacionamientos"
                }
            ]
        elif metrics.safe_parking_spots > 5:
            recommendations.parking_locations = [
                {
                    "name": f"Estacionamientos limitados en {zone_code}",
                    "address": "Pocas ubicaciones disponibles",
                    "security_level": "MEDIUM",
                    "capacity": metrics.safe_parking_spots,
                    "recommendation": "Planificar estacionamiento con anticipación"
                }
            ]
        else:
            recommendations.parking_locations = [
                {
                    "name": "Estacionamientos escasos",
                    "address": "Considerar zonas aledañas",
                    "security_level": "LOW",
                    "capacity": 0,
                    "recommendation": "Buscar alternativas de transporte o zonas cercanas"
                }
            ]

        return recommendations

    def calculate_crime_trend(self, zone_name: str, crime_gdf: gpd.GeoDataFrame) -> Tuple[TrendDirection, float]:
        """
        Calcular tendencia de criminalidad comparando datos históricos
        
        Args:
            zone_name: Nombre de la zona
            crime_gdf: GeoDataFrame con datos de criminalidad
            
        Returns:
            Tupla con dirección de tendencia y porcentaje de cambio
        """
        try:
            normalized_zone_name = normalize_locality_name(zone_name)
            zone_data = crime_gdf[crime_gdf['CMNOMLOCAL'].str.upper() == normalized_zone_name.upper()]
            
            if zone_data.empty:
                return TrendDirection.STABLE, 0.0
                
            zone_record = zone_data.iloc[0]
            
            # Comparar datos de 2024 vs 2025 (últimos años disponibles)
            crimes_2024 = 0
            crimes_2025 = 0
            
            # Sumar todos los tipos de crímenes para cada año
            crime_types = ['CMH', 'CMLP', 'CMHP', 'CMHR', 'CMHA', 'CMHB', 'CMHC', 'CMHM', 'CMDS', 'CMVI']
            for crime_type in crime_types:
                col_2024 = f'{crime_type}24CONT'
                col_2025 = f'{crime_type}25CONT'
                
                if col_2024 in zone_record.index and pd.notna(zone_record[col_2024]):
                    crimes_2024 += float(zone_record[col_2024])
                if col_2025 in zone_record.index and pd.notna(zone_record[col_2025]):
                    crimes_2025 += float(zone_record[col_2025])
            
            # Los datos de 2025 son de 6 meses, escalar a año completo para comparación
            crimes_2025_annualized = crimes_2025 * 2
            
            if crimes_2024 == 0:
                if crimes_2025_annualized > 0:
                    return TrendDirection.INCREASING, 100.0  # Aumento significativo desde 0
                else:
                    return TrendDirection.STABLE, 0.0
                
            # Calcular cambio porcentual
            change_pct = ((crimes_2025_annualized - crimes_2024) / crimes_2024) * 100
            
            # Determinar tendencia
            if change_pct > 15:
                trend = TrendDirection.INCREASING
            elif change_pct < -15:
                trend = TrendDirection.DECREASING
            else:
                trend = TrendDirection.STABLE
                
            return trend, round(change_pct, 1)
            
        except Exception as e:
            logger.warning(f"Error calculando tendencia para {zone_name}: {str(e)}")
            return TrendDirection.STABLE, 0.0

    def transform_all_zones_with_real_data(
        self,
        data: Dict[str, Any],
        calculation_date: datetime = None
    ) -> List[ZoneSafetyScore]:
        """
        Transformar datos para todas las zonas usando datos reales de criminalidad

        Args:
            data: Diccionario con todos los datos extraidos
            calculation_date: Fecha para calculos

        Returns:
            Lista de objetos ZoneSafetyScore
        """
        if calculation_date is None:
            calculation_date = datetime.now()

        # Cargar datos reales de criminalidad
        try:
            crime_gdf = load_real_crime_data()
        except FileNotFoundError:
            logger.error("No se pudieron cargar datos reales de criminalidad, usando método legacy")
            return self.transform_all_zones(data, calculation_date)

        # Obtener datos de zona e infraestructura
        localidades_gdf = data['localidades']
        bike_lanes_gdf = data['bike_lanes']
        parking_df = data['bike_parking']

        results = []

        # Procesar cada localidad
        for idx, zone in localidades_gdf.iterrows():
            zone_name = zone.get('LocNombre', f'Zone_{idx}')

            logger.info(f"Procesando zona con datos reales: {zone_name}")

            # Calcular métricas usando datos reales
            metrics = self.calculate_zone_metrics_real_data(
                zone_name,
                crime_gdf,
                bike_lanes_gdf,
                parking_df,
                calculation_date
            )

            # Calcular puntaje de seguridad
            safety_score, risk_level = self.calculate_safety_score(metrics)

            # Calcular tendencia usando datos históricos reales
            trend, trend_pct = self.calculate_crime_trend(zone_name, crime_gdf)

            # Generar recomendaciones
            recommendations = self.generate_recommendations(
                zone_name,
                metrics,
                risk_level,
                bike_lanes_gdf,
                parking_df
            )

            zone_safety_score = ZoneSafetyScore(
                zone_code=zone_name,
                zone_name=zone_name,
                calculation_date=calculation_date.date(),
                safety_score=safety_score,
                risk_level=risk_level,
                metrics=metrics,
                trend=trend,
                trend_percentage=trend_pct,
                recommendations=recommendations,
                created_at=calculation_date,
                updated_at=calculation_date
            )

            results.append(zone_safety_score)

        logger.info(f"Procesadas {len(results)} zonas con datos reales")
        return results

    def transform_all_zones(
        self,
        data: Dict[str, Any],
        calculation_date: datetime = None
    ) -> List[ZoneSafetyScore]:
        """
        Transformar datos para todas las zonas y calcular puntajes de seguridad (método legacy)

        Args:
            data: Diccionario con todos los datos extraidos
            calculation_date: Fecha para calculos

        Returns:
            Lista de objetos ZoneSafetyScore
        """
        if calculation_date is None:
            calculation_date = datetime.now()

        # Procesar datos de crimen (simulados)
        crimes_df = self.process_crime_data(data['crime_data'])

        # Obtener datos de zona
        localidades_gdf = data['localidades']
        bike_lanes_gdf = data['bike_lanes']
        parking_df = data['bike_parking']

        results = []

        # Procesar cada localidad
        for idx, zone in localidades_gdf.iterrows():
            zone_code = zone.get('LocNombre', f'Zone_{idx}')

            logger.info(f"Procesando zona: {zone_code}")

            # Calcular metricas
            metrics = self.calculate_zone_metrics(
                zone_code,
                localidades_gdf,
                crimes_df,
                bike_lanes_gdf,
                parking_df,
                calculation_date
            )

            # Calcular puntaje de seguridad
            safety_score, risk_level = self.calculate_safety_score(metrics)

            # Calcular tendencia (necesitaria datos historicos en produccion)
            trend, trend_pct = TrendDirection.STABLE, 0.0

            # Generar recomendaciones
            recommendations = self.generate_recommendations(
                zone_code,
                metrics,
                risk_level,
                crimes_df,
                parking_df
            )

            # Crear objeto ZoneSafetyScore
            zone_score = ZoneSafetyScore(
                zone_code=zone_code,
                zone_name=zone_code,
                zone_type="LOCALIDAD",
                calculation_date=calculation_date.date(),
                safety_score=safety_score,
                risk_level=risk_level,
                metrics=metrics,
                trend=trend,
                trend_percentage=trend_pct,
                recommendations=recommendations,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )

            results.append(zone_score)

        logger.info(f"Procesadas {len(results)} zonas")
        return results


# Funcion de conveniencia para uso independiente
def transform_data(
    data: Dict[str, Any],
    calculation_date: Optional[datetime] = None
) -> List[ZoneSafetyScore]:
    """
    Transformar todos los datos y calcular puntajes de seguridad

    Args:
        data: Diccionario con datos extraidos
        calculation_date: Fecha para calculos

    Returns:
        Lista de objetos ZoneSafetyScore
    """
    transformer = DataTransformer()
    return transformer.transform_all_zones(data, calculation_date)