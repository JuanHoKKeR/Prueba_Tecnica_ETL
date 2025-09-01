"""
Anomaly detection service for identifying unusual patterns in zone safety
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import logging

logger = logging.getLogger(__name__)


class ZoneAnomalyDetector:
    """Detect anomalies in zone safety patterns using ML"""
    
    def detect_theft_anomalies(self, zone_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Detecta anomalías en patrones de robo usando Isolation Forest
        
        Útil para: Identificar zonas con comportamiento inusual que requieren
        atención especial (ej: aumento súbito de robos)
        """
        if len(zone_data) < 10:
            return {"status": "insufficient_data"}
        
        # Preparar features
        features = zone_data[[
            'thefts_last_30_days',
            'theft_density_per_km2',
            'bike_lane_coverage_km',
            'safe_parking_spots'
        ]].fillna(0)
        
        # Normalizar datos
        scaler = StandardScaler()
        features_scaled = scaler.fit_transform(features)
        
        # Entrenar modelo de detección de anomalías
        iso_forest = IsolationForest(
            contamination=0.1,  # Esperamos 10% de anomalías
            random_state=42
        )
        
        # Predecir anomalías (-1 = anomalía, 1 = normal)
        zone_data['anomaly'] = iso_forest.fit_predict(features_scaled)
        zone_data['anomaly_score'] = iso_forest.score_samples(features_scaled)
        
        # Identificar zonas anómalas
        anomalous_zones = zone_data[zone_data['anomaly'] == -1]
        
        results = {
            "total_zones": len(zone_data),
            "anomalous_zones": len(anomalous_zones),
            "anomalies": []
        }
        
        for _, zone in anomalous_zones.iterrows():
            anomaly_info = {
                "zone": zone['zone_code'],
                "anomaly_score": float(zone['anomaly_score']),
                "reason": self._identify_anomaly_reason(zone, zone_data),
                "recommendation": self._generate_anomaly_recommendation(zone)
            }
            results["anomalies"].append(anomaly_info)
        
        logger.info(f"Detected {len(anomalous_zones)} anomalous zones")
        return results
    
    def _identify_anomaly_reason(self, zone: pd.Series, all_zones: pd.DataFrame) -> str:
        """Identifica por qué una zona es anómala"""
        reasons = []
        
        # Comparar con la mediana
        median_thefts = all_zones['thefts_last_30_days'].median()
        median_density = all_zones['theft_density_per_km2'].median()
        
        if zone['thefts_last_30_days'] > median_thefts * 2:
            reasons.append(f"Robos excesivos: {zone['thefts_last_30_days']} vs mediana {median_thefts:.0f}")
        
        if zone['theft_density_per_km2'] > median_density * 2:
            reasons.append(f"Densidad criminal alta: {zone['theft_density_per_km2']:.1f}/km²")
        
        if zone['bike_lane_coverage_km'] < 5 and zone['thefts_last_30_days'] > median_thefts:
            reasons.append("Alta criminalidad con poca infraestructura")
        
        return " | ".join(reasons) if reasons else "Patrón inusual detectado"
    
    def _generate_anomaly_recommendation(self, zone: pd.Series) -> str:
        """Genera recomendaciones para zonas anómalas"""
        if zone['thefts_last_30_days'] > 50:
            return "ALERTA: Requiere seguro adicional y restricción de horarios"
        elif zone['theft_density_per_km2'] > 10:
            return "PRECAUCIÓN: Implementar GPS tracking obligatorio"
        else:
            return "MONITOREAR: Revisar tendencia en próximas semanas"
    
    def cluster_zones(self, zone_data: pd.DataFrame, n_clusters: int = 4) -> Dict[str, Any]:
        """
        Agrupa zonas en clusters similares usando K-Means
        
        Útil para: Estrategias diferenciadas por tipo de zona
        """
        if len(zone_data) < n_clusters:
            return {"status": "insufficient_data"}
        
        # Features para clustering
        features = zone_data[[
            'safety_score',
            'theft_density_per_km2',
            'bike_lane_density_per_km2',
            'parking_density_per_km2'
        ]].fillna(0)
        
        # Normalizar
        scaler = StandardScaler()
        features_scaled = scaler.fit_transform(features)
        
        # Aplicar K-Means
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        zone_data['cluster'] = kmeans.fit_predict(features_scaled)
        
        # Analizar clusters
        clusters = {}
        for cluster_id in range(n_clusters):
            cluster_zones = zone_data[zone_data['cluster'] == cluster_id]
            
            clusters[f"cluster_{cluster_id}"] = {
                "zones": cluster_zones['zone_code'].tolist(),
                "size": len(cluster_zones),
                "avg_safety_score": float(cluster_zones['safety_score'].mean()),
                "avg_thefts": float(cluster_zones['thefts_last_30_days'].mean()),
                "characteristics": self._describe_cluster(cluster_zones),
                "strategy": self._recommend_cluster_strategy(cluster_zones)
            }
        
        return {
            "n_clusters": n_clusters,
            "clusters": clusters,
            "optimal_clusters": self._find_optimal_clusters(features_scaled)
        }
    
    def _describe_cluster(self, cluster_data: pd.DataFrame) -> str:
        """Describe las características de un cluster"""
        avg_score = cluster_data['safety_score'].mean()
        avg_thefts = cluster_data['thefts_last_30_days'].mean()
        
        if avg_score > 70:
            return "Zonas seguras con buena infraestructura"
        elif avg_score > 50:
            return "Zonas de riesgo moderado"
        elif avg_thefts > 100:
            return "Zonas de alto riesgo criminal"
        else:
            return "Zonas en desarrollo"
    
    def _recommend_cluster_strategy(self, cluster_data: pd.DataFrame) -> str:
        """Recomienda estrategia para cada cluster"""
        avg_score = cluster_data['safety_score'].mean()
        
        if avg_score > 70:
            return "Expansión agresiva - zona prioritaria"
        elif avg_score > 50:
            return "Operación estándar con monitoreo"
        elif avg_score > 30:
            return "Operación limitada - horario restringido"
        else:
            return "No operar o requiere intervención especial"
    
    def _find_optimal_clusters(self, features_scaled: np.ndarray) -> int:
        """Encuentra el número óptimo de clusters usando método del codo"""
        if len(features_scaled) < 10:
            return 3
        
        inertias = []
        K_range = range(2, min(8, len(features_scaled)))
        
        for k in K_range:
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            kmeans.fit(features_scaled)
            inertias.append(kmeans.inertia_)
        
        # Método del codo simplificado
        # Buscar el punto donde la reducción de inercia se estabiliza
        if len(inertias) > 2:
            diffs = np.diff(inertias)
            diffs2 = np.diff(diffs)
            optimal = np.argmin(diffs2) + 2  # +2 porque empezamos en k=2
        else:
            optimal = 3
        
        return int(optimal)
    
    def predict_trend(self, zone_code: str, historical_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Predice tendencia futura simple usando regresión lineal
        
        Útil para: Anticipar zonas que mejorarán o empeorarán
        """
        zone_history = historical_data[historical_data['zone_code'] == zone_code]
        
        if len(zone_history) < 3:
            return {"status": "insufficient_history"}
        
        # Preparar datos temporales
        zone_history = zone_history.sort_values('calculation_date')
        zone_history['days_from_start'] = (
            zone_history['calculation_date'] - zone_history['calculation_date'].min()
        ).dt.days
        
        # Regresión lineal simple
        X = zone_history['days_from_start'].values.reshape(-1, 1)
        y = zone_history['thefts_last_30_days'].values
        
        # Calcular tendencia manualmente (sin sklearn para simplicidad)
        n = len(X)
        x_mean = X.mean()
        y_mean = y.mean()
        
        numerator = sum((X[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((X[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            slope = 0
        else:
            slope = numerator / denominator
        
        intercept = y_mean - slope * x_mean
        
        # Predecir próximos 30 días
        next_30_days = X[-1] + 30
        prediction = slope * next_30_days + intercept
        
        # Clasificar tendencia
        if slope < -0.5:
            trend = "MEJORANDO_SIGNIFICATIVAMENTE"
        elif slope < -0.1:
            trend = "MEJORANDO"
        elif slope > 0.5:
            trend = "EMPEORANDO_SIGNIFICATIVAMENTE"
        elif slope > 0.1:
            trend = "EMPEORANDO"
        else:
            trend = "ESTABLE"
        
        return {
            "zone": zone_code,
            "current_thefts": float(y[-1]),
            "predicted_thefts_30d": float(max(0, prediction)),
            "trend": trend,
            "slope": float(slope),
            "confidence": self._calculate_confidence(zone_history),
            "recommendation": self._trend_recommendation(trend, prediction)
        }
    
    def _calculate_confidence(self, data: pd.DataFrame) -> str:
        """Calcula confianza de la predicción"""
        if len(data) >= 12:
            return "HIGH"
        elif len(data) >= 6:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _trend_recommendation(self, trend: str, predicted_thefts: float) -> str:
        """Genera recomendación basada en tendencia"""
        if "MEJORANDO" in trend:
            return "Oportunidad de expansión - zona en mejora"
        elif "EMPEORANDO_SIGNIFICATIVAMENTE" in trend:
            return "Alerta - considerar suspender operaciones"
        elif "EMPEORANDO" in trend:
            return "Precaución - aumentar medidas de seguridad"
        else:
            return "Mantener operación actual"


# Función para agregar al endpoint de la API
async def analyze_with_ml(zone_code: str, db_connection) -> Dict[str, Any]:
    """
    Endpoint para análisis con ML
    """
    detector = ZoneAnomalyDetector()
    
    # Obtener datos de todas las zonas
    query = "SELECT * FROM zone_safety_scores WHERE calculation_date = CURRENT_DATE"
    zone_data = pd.read_sql(query, db_connection)
    
    # 1. Detección de anomalías
    anomalies = detector.detect_theft_anomalies(zone_data)
    
    # 2. Clustering
    clusters = detector.cluster_zones(zone_data)
    
    # 3. Predicción de tendencia (si hay datos históricos)
    historical_query = f"""
        SELECT * FROM zone_safety_scores 
        WHERE zone_code = '{zone_code}'
        ORDER BY calculation_date DESC
        LIMIT 30
    """
    historical_data = pd.read_sql(historical_query, db_connection)
    trend_prediction = detector.predict_trend(zone_code, historical_data)
    
    return {
        "zone": zone_code,
        "ml_analysis": {
            "anomaly_detection": anomalies,
            "clustering": clusters,
            "trend_prediction": trend_prediction
        },
        "insights": generate_ml_insights(anomalies, clusters, trend_prediction)
    }


def generate_ml_insights(anomalies: Dict, clusters: Dict, trend: Dict) -> List[str]:
    """Genera insights accionables del análisis ML"""
    insights = []
    
    # Insight de anomalías
    if anomalies.get("anomalous_zones", 0) > 0:
        insights.append(f"⚠️ {anomalies['anomalous_zones']} zonas con comportamiento anómalo requieren atención inmediata")
    
    # Insight de clusters
    if clusters.get("clusters"):
        high_priority = [c for c in clusters["clusters"].values() if c["avg_safety_score"] > 70]
        if high_priority:
            insights.append(f"✅ {len(high_priority)} grupos de zonas óptimas para expansión identificados")
    
    # Insight de tendencia
    if trend.get("trend") == "MEJORANDO_SIGNIFICATIVAMENTE":
        insights.append(f"📈 Zona mejorando rápidamente - oportunidad de inversión")
    elif "EMPEORANDO" in trend.get("trend", ""):
        insights.append(f"📉 Tendencia negativa detectada - revisar estrategia de seguridad")
    
    return insights