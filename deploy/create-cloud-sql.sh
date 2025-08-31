#!/bin/bash
# Script para crear la instancia de Cloud SQL para Roda Analytics

# Variables de configuración
PROJECT_ID="${GCP_PROJECT_ID:-YOUR_PROJECT_ID}"
INSTANCE_NAME="${CLOUD_SQL_INSTANCE:-roda-analytics-db}"
REGION="${GCP_REGION:-us-central1}"
TIER="${DB_TIER:-db-f1-micro}"  # Instancia pequeña para pruebas
DB_VERSION="${DB_VERSION:-POSTGRES_14}"
ROOT_PASSWORD="${DB_ROOT_PASSWORD:-YOUR_ROOT_PASSWORD}"  # Cambiar en producción
DATABASE_NAME="${DATABASE_NAME:-roda_analytics}"
DB_USER="${DB_USER:-roda_user}"
DB_PASSWORD="${DB_PASSWORD:-YOUR_DB_PASSWORD}"  # Cambiar en producción

echo "🚀 Creando instancia Cloud SQL para Roda Analytics..."

# 1. Crear la instancia de Cloud SQL
echo "📦 Creando instancia PostgreSQL..."
gcloud sql instances create $INSTANCE_NAME \
    --database-version=$DB_VERSION \
    --tier=$TIER \
    --region=$REGION \
    --root-password=$ROOT_PASSWORD \
    --storage-type=SSD \
    --storage-size=10GB \
    --availability-type=zonal \
    --backup-start-time=02:00 \
    --maintenance-window-day=SUN \
    --maintenance-window-hour=03 \
    --deletion-protection

# 2. Crear la base de datos
echo "🗄️ Creando base de datos $DATABASE_NAME..."
gcloud sql databases create $DATABASE_NAME \
    --instance=$INSTANCE_NAME

# 3. Crear el usuario de aplicación
echo "👤 Creando usuario $DB_USER..."
gcloud sql users create $DB_USER \
    --instance=$INSTANCE_NAME \
    --password=$DB_PASSWORD

# 4. Obtener la IP de conexión
echo "🌐 Obteniendo IP de conexión..."
INSTANCE_IP=$(gcloud sql instances describe $INSTANCE_NAME \
    --format="value(ipAddresses[0].ipAddress)")

echo "✅ Instancia creada exitosamente!"
echo "📋 Detalles de conexión:"
echo "   - Instancia: $INSTANCE_NAME"
echo "   - IP: $INSTANCE_IP"
echo "   - Base de datos: $DATABASE_NAME"
echo "   - Usuario: $DB_USER"
echo "   - Región: $REGION"
echo ""
echo "🔧 Siguiente paso: Configurar PostGIS y ejecutar init.sql"
