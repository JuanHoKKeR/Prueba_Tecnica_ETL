#!/bin/bash
# Script para configurar Cloud Scheduler para actualizaciones automáticas

PROJECT_ID="${GCP_PROJECT_ID:-YOUR_PROJECT_ID}"
SERVICE_NAME="${SERVICE_NAME:-roda-analytics}"
REGION="${GCP_REGION:-us-central1}"
JOB_NAME="${SCHEDULER_JOB_NAME:-roda-daily-update}"

echo "⏰ Configurando Cloud Scheduler..."

# Obtener URL del servicio Cloud Run
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --format="value(status.url)")

# 1. Crear job para actualización diaria
echo "📅 Creando job de actualización diaria..."
gcloud scheduler jobs create http $JOB_NAME \
    --location=$REGION \
    --schedule="0 6 * * *" \
    --uri="$SERVICE_URL/process" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{
        "mode": "BATCH",
        "zones": [],
        "force_refresh": true,
        "time_range": null
    }' \
    --description="Actualización diaria automática de métricas de seguridad"

# 2. Crear job para actualización semanal completa  
echo "📊 Creando job de actualización semanal..."
gcloud scheduler jobs create http roda-weekly-full-update \
    --location=$REGION \
    --schedule="0 2 * * 0" \
    --uri="$SERVICE_URL/process" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{
        "mode": "BATCH", 
        "zones": [],
        "force_refresh": true,
        "time_range": {
            "start_date": "2025-01-01T00:00:00",
            "end_date": "2025-06-30T23:59:59"
        }
    }' \
    --description="Actualización semanal completa todos los domingos"

echo "✅ Cloud Scheduler configurado!"
echo "📅 Jobs creados:"
echo "  - $JOB_NAME: Diario a las 6:00 AM"
echo "  - roda-weekly-full-update: Domingos a las 2:00 AM"
echo ""
echo "🌐 Ver jobs: https://console.cloud.google.com/cloudscheduler?project=$PROJECT_ID"
