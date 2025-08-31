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

from ..config.settings import settings
from ..models.schemas import (
    RiskLevel, TrendDirection, SafetyMetrics,
    SafetyRecommendations, ZoneSafetyScore
)

logger = logging.getLogger(__name__)


class DataTransformer:
    """Clase para manejar transformacion de datos y calculo de puntajes de seguridad"""

    def __init__(self):
        self.risk_thresholds = settings.risk_thresholds  # Umbrales de riesgo desde settings

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

        # Convertir strings de fecha a datetime
        df['incident_date'] = pd.to_datetime(df['incident_date'])

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
        Calcular metricas de seguridad para una zona especifica

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
        zone = zone_gdf[zone_gdf['Nombre'] == zone_code]
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
        zone_crimes = recent_crimes[
            recent_crimes.get('barrio', '').str.contains(zone_code, na=False) |
            recent_crimes.get('zona', '').str.contains(zone_code, na=False)
        ]

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

        bike_lane_km = zone_lanes['length_km'].sum() if not zone_lanes.empty else 0
        bike_lane_density = bike_lane_km / zone_area if zone_area > 0 else 0

        # Calcular metricas de estacionamientos
        # Por simplicidad, contar todos los estacionamientos en el nombre de zona
        zone_parking = parking_df[
            parking_df.get('localidad', '').str.contains(zone_code, na=False)
        ]

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

        # Penalizar por robos (max -50 puntos)
        theft_penalty = min(metrics.thefts_last_30_days * 2, 50)
        score -= theft_penalty

        # Penalizar por densidad de robos (max -20 puntos)
        density_penalty = min(metrics.theft_density_per_km2 * 5, 20)
        score -= density_penalty

        # Recompensar por infraestructura de estacionamientos (max +15 puntos)
        parking_bonus = min(metrics.parking_density_per_km2 * 3, 15)
        score += parking_bonus

        # Recompensar por infraestructura de ciclorutas (max +15 puntos)
        bikelane_bonus = min(metrics.bike_lane_density_per_km2 * 3, 15)
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
        crimes_df: pd.DataFrame,
        parking_df: pd.DataFrame
    ) -> SafetyRecommendations:
        """
        Generar recomendaciones de seguridad para una zona

        Args:
            zone_code: Identificador de zona
            metrics: Metricas de seguridad de zona
            risk_level: Nivel de riesgo calculado
            crimes_df: DataFrame con incidentes de crimen
            parking_df: DataFrame con ubicaciones de estacionamientos

        Returns:
            Objeto SafetyRecommendations
        """
        recommendations = SafetyRecommendations()

        # Analizar patrones de crimen por hora
        zone_crimes = crimes_df[
            crimes_df.get('barrio', '').str.contains(zone_code, na=False)
        ]

        if not zone_crimes.empty:
            # Encontrar horas mas seguras (simplificado - deberia analizar timestamps reales)
            # Para demo, sugeriremos horas de commute estandar para zonas de bajo riesgo
            if risk_level in [RiskLevel.VERY_LOW, RiskLevel.LOW]:
                recommendations.best_hours = [
                    "5:00 AM - 9:00 AM",
                    "12:00 PM - 2:00 PM",
                    "5:00 PM - 7:00 PM"
                ]
            else:
                recommendations.best_hours = [
                    "6:00 AM - 8:00 AM",
                    "12:00 PM - 1:00 PM"
                ]

            # Identificar areas problemáticas
            if risk_level in [RiskLevel.HIGH, RiskLevel.VERY_HIGH]:
                recommendations.avoid_areas = [
                    "Áreas con poca iluminación después de 6 PM",
                    "Calles sin cicloruta dedicada",
                    "Zonas industriales los fines de semana"
                ]

        # Recomendar rutas seguras basado en cobertura de ciclorutas
        if metrics.bike_lane_coverage_km > 5:
            recommendations.safe_routes = [
                "Rutas con cicloruta segregada",
                "Corredores verdes principales",
                "Vías con semáforos para ciclistas"
            ]
        else:
            recommendations.safe_routes = [
                "Calles con bajo flujo vehicular",
                "Rutas con buena visibilidad",
                "Vías principales con berma amplia"
            ]

        # Recomendar ubicaciones de estacionamiento
        zone_parking = parking_df[
            parking_df.get('localidad', '').str.contains(zone_code, na=False)
        ]

        if not zone_parking.empty:
            # Tomar top 5 estacionamientos
            parking_list = []
            for _, parking in zone_parking.head(5).iterrows():
                parking_list.append({
                    "name": parking.get('nombre', 'Parqueadero'),
                    "address": parking.get('direccion', 'N/A'),
                    "security_level": "MEDIUM",  # Se calcularia basado en datos reales
                    "capacity": parking.get('capacidad', 0)
                })
            recommendations.parking_locations = parking_list

        return recommendations

    def transform_all_zones(
        self,
        data: Dict[str, Any],
        calculation_date: datetime = None
    ) -> List[ZoneSafetyScore]:
        """
        Transformar datos para todas las zonas y calcular puntajes de seguridad

        Args:
            data: Diccionario con todos los datos extraidos
            calculation_date: Fecha para calculos

        Returns:
            Lista de objetos ZoneSafetyScore
        """
        if calculation_date is None:
            calculation_date = datetime.now()

        # Procesar datos de crimen
        crimes_df = self.process_crime_data(data['crime_data'])

        # Obtener datos de zona
        localidades_gdf = data['localidades']
        bike_lanes_gdf = data['bike_lanes']
        parking_df = data['bike_parking']

        results = []

        # Procesar cada localidad
        for idx, zone in localidades_gdf.iterrows():
            zone_code = zone.get('Nombre', f'Zone_{idx}')

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