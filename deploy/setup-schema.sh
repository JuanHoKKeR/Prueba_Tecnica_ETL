#!/bin/bash
# Script para configurar PostGIS y ejecutar el schema inicial

# Variables de configuración
PROJECT_ID="${GCP_PROJECT_ID:-YOUR_PROJECT_ID}"
INSTANCE_NAME="${CLOUD_SQL_INSTANCE:-roda-analytics-db}"
DATABASE_NAME="${DATABASE_NAME:-roda_analytics}"
DB_USER="${DB_USER:-roda_user}"

echo "🔧 Configurando PostGIS y schema inicial..."

# 1. Conectar y habilitar PostGIS
echo "📍 Habilitando extensión PostGIS..."
gcloud sql connect $INSTANCE_NAME --user=postgres --database=$DATABASE_NAME <<SQL
-- Habilitar PostGIS (equivalente a postgis/postgis:15-3.3)
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS postgis_raster;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;

-- Verificar PostGIS instalado
SELECT PostGIS_Version();
SQL

# 2. Ejecutar el schema inicial
echo "🗄️ Ejecutando schema inicial desde init.sql..."
echo "⚠️  Ejecuta manualmente:"
echo "   gcloud sql connect $INSTANCE_NAME --user=$DB_USER --database=$DATABASE_NAME"
echo "   Luego copia y pega el contenido de sql/init.sql"

echo ""
echo "🔗 Para conectar desde tu aplicación:"
echo "   Host: $(gcloud sql instances describe $INSTANCE_NAME --format='value(ipAddresses[0].ipAddress)')"
echo "   Puerto: 5432"
echo "   Base de datos: $DATABASE_NAME"
echo "   Usuario: $DB_USER"
