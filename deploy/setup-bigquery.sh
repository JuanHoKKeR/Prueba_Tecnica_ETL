#!/bin/bash
# Script para configurar BigQuery para analytics avanzados

PROJECT_ID="${GCP_PROJECT_ID:-YOUR_PROJECT_ID}"
DATASET_NAME="${BIGQUERY_DATASET:-roda_analytics}"
LOCATION="${BIGQUERY_LOCATION:-US}"

echo "📊 Configurando BigQuery para Roda Analytics..."

# 1. Crear dataset en BigQuery
echo "📦 Creando dataset $DATASET_NAME..."
bq mk --dataset \
    --location=$LOCATION \
    --description="Dataset para análisis de seguridad ciclista Roda" \
    $PROJECT_ID:$DATASET_NAME

# 2. Crear tabla para zona safety scores
echo "🗄️ Creando tabla zone_safety_scores..."
bq mk --table \
    $PROJECT_ID:$DATASET_NAME.zone_safety_scores \
    zone_code:STRING,calculation_date:DATE,safety_score:FLOAT,risk_level:STRING,thefts_last_7_days:INTEGER,thefts_last_30_days:INTEGER,thefts_last_90_days:INTEGER,theft_density_per_km2:FLOAT,bike_lane_coverage_km:FLOAT,bike_lane_density_per_km2:FLOAT,safe_parking_spots:INTEGER,parking_density_per_km2:FLOAT,trend:STRING,trend_percentage:FLOAT,best_hours:STRING,safe_routes:STRING,avoid_areas:STRING,parking_locations:STRING,created_at:TIMESTAMP,updated_at:TIMESTAMP

# 3. Crear tabla para crime incidents
echo "🚨 Creando tabla crime_incidents..."
bq mk --table \
    $PROJECT_ID:$DATASET_NAME.crime_incidents \
    incident_date:TIMESTAMP,incident_type:STRING,modalidad:STRING,localidad:STRING,upz:STRING,barrio:STRING,zona:STRING,latitude:FLOAT,longitude:FLOAT,source:STRING,created_at:TIMESTAMP

# 4. Crear vista agregada para dashboards
echo "📈 Creando vista agregada..."
bq query --use_legacy_sql=false \
"CREATE OR REPLACE VIEW \`$PROJECT_ID.$DATASET_NAME.monthly_safety_trends\` AS
SELECT 
  zone_code,
  EXTRACT(YEAR FROM calculation_date) as year,
  EXTRACT(MONTH FROM calculation_date) as month,
  AVG(safety_score) as avg_safety_score,
  AVG(theft_density_per_km2) as avg_theft_density,
  COUNT(*) as records_count
FROM \`$PROJECT_ID.$DATASET_NAME.zone_safety_scores\`
GROUP BY zone_code, year, month
ORDER BY year DESC, month DESC, avg_safety_score ASC"

echo "✅ BigQuery configurado exitosamente!"
echo "📊 Dataset: $PROJECT_ID:$DATASET_NAME"
echo "🌐 Console: https://console.cloud.google.com/bigquery?project=$PROJECT_ID"
