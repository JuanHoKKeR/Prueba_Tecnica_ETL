"""
Pruebas unitarias para los endpoints principales de la API
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import json

from src.main import app
from src.models.schemas import JobStatus, RiskLevel


client = TestClient(app)


def test_root_endpoint():
    """Prueba que el endpoint raíz devuelva la info correcta"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data
    assert data["message"] == "Roda Zone Analytics API"


def test_health_endpoint():
    """Prueba el endpoint de salud para ver si todo está bien"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert "version" in data
    assert "database" in data
    assert "timestamp" in data


def test_process_batch_endpoint():
    """Prueba el endpoint de procesamiento en lote"""
    request_data = {
        "mode": "BATCH",
        "zones": ["CHAPINERO", "USAQUEN"],
        "force_refresh": False
    }
    
    response = client.post("/process", json=request_data)
    assert response.status_code == 200
    
    data = response.json()
    assert "job_id" in data
    assert "status" in data
    assert data["status"] == "PENDING"
    assert "started_at" in data
    assert "estimated_completion" in data


def test_process_with_time_range():
    """Prueba el procesamiento en lote con un rango de tiempo específico"""
    request_data = {
        "mode": "BATCH",
        "time_range": {
            "start_date": "2024-10-01T00:00:00",
            "end_date": "2024-12-31T23:59:59"
        },
        "zones": ["SUBA"],
        "force_refresh": True
    }
    
    response = client.post("/process", json=request_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["job_id"] is not None
    assert data["message"] == "Processing started in background"


def test_get_job_status():
    """Prueba el endpoint para obtener el estado de un trabajo"""
    # Primero creamos un trabajo
    response = client.post("/process", json={"mode": "BATCH"})
    job_id = response.json()["job_id"]
    
    # Luego verificamos su estado
    response = client.get(f"/process/{job_id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["job_id"] == job_id
    assert data["status"] in ["PENDING", "RUNNING", "COMPLETED", "FAILED"]


def test_get_invalid_job_status():
    """Prueba el endpoint de estado con un ID de trabajo inválido"""
    response = client.get("/process/invalid-job-id")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_list_zones():
    """Prueba el endpoint para listar zonas, con límite"""
    response = client.get("/zones?limit=5")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 5


def test_list_zones_with_filter():
    """Prueba listar zonas filtradas por nivel de riesgo"""
    response = client.get("/zones?risk_level=HIGH&limit=10")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)
    # Todas las zonas devueltas deberían tener riesgo HIGH
    for zone in data:
        if "risk_level" in zone:
            assert zone["risk_level"] == "HIGH"


def test_get_safe_routes():
    """Prueba el endpoint de recomendaciones de rutas seguras"""
    response = client.get(
        "/recommendations/safe-routes",
        params={
            "origin_zone": "CHAPINERO",
            "destination_zone": "USAQUEN"
        }
    )
    assert response.status_code == 200
    
    data = response.json()
    assert "origin" in data
    assert "destination" in data
    assert "recommended_routes" in data
    assert isinstance(data["recommended_routes"], list)
    
    # Verificamos la estructura de la ruta
    if len(data["recommended_routes"]) > 0:
        route = data["recommended_routes"][0]
        assert "name" in route
        assert "safety_score" in route
        assert "distance_km" in route
        assert "features" in route


def test_invalid_endpoint():
    """Prueba que endpoints inválidos devuelvan 404"""
    response = client.get("/invalid-endpoint")
    assert response.status_code == 404


def test_process_invalid_mode():
    """Prueba el endpoint de proceso con un modo inválido"""
    request_data = {
        "mode": "INVALID_MODE",
        "zones": ["CHAPINERO"]
    }
    
    response = client.post("/process", json=request_data)
    assert response.status_code == 422  # Error de validación


def test_process_invalid_time_range():
    """Prueba el proceso con un rango de tiempo inválido (fin antes del inicio)"""
    request_data = {
        "mode": "BATCH",
        "time_range": {
            "start_date": "2024-12-31T00:00:00",
            "end_date": "2024-01-01T00:00:00"  # Fin antes del inicio, ¡qué lío!
        }
    }
    
    response = client.post("/process", json=request_data)
    assert response.status_code == 422  # Error de validación


def test_analyze_zone_endpoint():
    """Prueba el endpoint de análisis de zona específica"""
    response = client.get("/analyze/CHAPINERO")
    assert response.status_code == 200
    
    data = response.json()
    assert "zone_analysis" in data
    
    zone_analysis = data["zone_analysis"]
    assert "zone_code" in zone_analysis
    assert "safety_score" in zone_analysis
    assert "risk_level" in zone_analysis
    assert "metrics" in zone_analysis
    assert "recommendations" in zone_analysis
    
    # Verificar que el safety_score esté en rango válido
    assert 0 <= zone_analysis["safety_score"] <= 100


def test_analyze_invalid_zone():
    """Prueba el análisis de una zona que no existe"""
    response = client.get("/analyze/ZONA_INEXISTENTE")
    assert response.status_code == 404