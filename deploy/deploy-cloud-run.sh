#!/bin/bash
# Script para desplegar a Cloud Run con todas las variables de entorno

PROJECT_ID="${GCP_PROJECT_ID:-YOUR_PROJECT_ID}"
SERVICE_NAME="${SERVICE_NAME:-roda-analytics}"
REGION="${GCP_REGION:-us-central1}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE="us-central1-docker.pkg.dev/$PROJECT_ID/roda-repo/zone-analytics:$IMAGE_TAG"

echo "🚀 Desplegando $SERVICE_NAME a Cloud Run..."

# Desplegar con todas las variables de entorno
gcloud run deploy $SERVICE_NAME \
    --image=$IMAGE \
    --platform=managed \
    --region=$REGION \
    --port=8080 \
    --memory=2Gi \
    --cpu=2 \
    --min-instances=1 \
    --max-instances=5 \
    --timeout=600 \
    --concurrency=50 \
    --set-env-vars="DATABASE_URL=${DATABASE_URL}" \
    --set-env-vars="POSTGRES_HOST=${POSTGRES_HOST}" \
    --set-env-vars="POSTGRES_PORT=${POSTGRES_PORT:-5432}" \
    --set-env-vars="POSTGRES_USER=${POSTGRES_USER}" \
    --set-env-vars="POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
    --set-env-vars="POSTGRES_DB=${POSTGRES_DB}" \
    --set-env-vars="API_HOST=0.0.0.0" \
    --set-env-vars="API_PORT=8080" \
    --set-env-vars="API_ENV=production" \
    --set-env-vars="LOG_LEVEL=INFO" \
    --set-env-vars="CACHE_DIR=/tmp/roda_cache" \
    --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID" \
    --set-env-vars="CRIME_DATA_URL=${CRIME_DATA_URL}" \
    --allow-unauthenticated

# Obtener URL del servicio
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --format="value(status.url)")

echo "✅ Despliegue completado!"
echo "🌐 URL del servicio: $SERVICE_URL"
echo ""
echo "🧪 Comandos de prueba:"
echo "curl $SERVICE_URL/health"
echo "curl $SERVICE_URL/data-availability"
echo "curl $SERVICE_URL/analyze/KENNEDY"
