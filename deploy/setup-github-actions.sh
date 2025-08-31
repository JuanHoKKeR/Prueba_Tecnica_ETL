#!/bin/bash
# 🔧 Setup GitHub Actions para RODA Analytics
# Este script configura los secrets necesarios para CI/CD

set -e

PROJECT_ID="focus-chain-470709-q6"
SERVICE_ACCOUNT_NAME="github-actions-sa"
SERVICE_ACCOUNT_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"

echo "🔧 Configurando GitHub Actions para RODA Analytics..."
echo "=================================================="

# ====================================
# 🔐 1. CREAR SERVICE ACCOUNT
# ====================================
echo
echo "🔐 1. Creando Service Account para GitHub Actions..."

# Crear service account si no existe
if ! gcloud iam service-accounts describe $SERVICE_ACCOUNT_EMAIL --project=$PROJECT_ID &>/dev/null; then
    gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
        --display-name="GitHub Actions Service Account" \
        --description="Service account para CI/CD pipeline de RODA Analytics" \
        --project=$PROJECT_ID
    echo "✅ Service Account creado: $SERVICE_ACCOUNT_EMAIL"
else
    echo "ℹ️ Service Account ya existe: $SERVICE_ACCOUNT_EMAIL"
fi

# ====================================
# 🎯 2. ASIGNAR ROLES NECESARIOS
# ====================================
echo
echo "🎯 2. Asignando roles necesarios..."

ROLES=(
    "roles/run.admin"                    # Cloud Run deployment
    "roles/storage.admin"                # Artifact Registry
    "roles/iam.serviceAccountUser"       # Service account usage
    "roles/cloudsql.client"              # Cloud SQL access
    "roles/bigquery.dataEditor"          # BigQuery access
    "roles/bigquery.jobUser"             # BigQuery jobs
    "roles/cloudscheduler.admin"         # Scheduler management
)

for role in "${ROLES[@]}"; do
    echo "📝 Asignando rol: $role"
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
        --role="$role" \
        --quiet
done

# ====================================
# 🗝️ 3. GENERAR CLAVE JSON
# ====================================
echo
echo "🗝️ 3. Generando clave JSON..."

KEY_FILE="github-actions-key.json"
gcloud iam service-accounts keys create $KEY_FILE \
    --iam-account=$SERVICE_ACCOUNT_EMAIL \
    --project=$PROJECT_ID

echo "✅ Clave generada: $KEY_FILE"

# ====================================
# 📋 4. MOSTRAR SECRETS PARA GITHUB
# ====================================
echo
echo "📋 4. SECRETS PARA CONFIGURAR EN GITHUB:"
echo "========================================"
echo
echo "Ve a: https://github.com/JuanHoKKeR/Prueba_Tecnica_ETL/settings/secrets/actions"
echo
echo "🔐 Secrets a configurar:"
echo

echo "Name: GCP_SERVICE_ACCOUNT_KEY"
echo "Value:"
cat $KEY_FILE | base64 -w 0
echo
echo

echo "Name: DATABASE_URL"
echo "Value: postgresql://roda_user:123456?pruebaRODA@34.72.167.164:5432/roda_analytics"
echo

echo "Name: POSTGRES_HOST"
echo "Value: 34.72.167.164"
echo

echo "Name: POSTGRES_PORT"
echo "Value: 5432"
echo

echo "Name: POSTGRES_USER"
echo "Value: roda_user"
echo

echo "Name: POSTGRES_PASSWORD"
echo "Value: 123456?pruebaRODA"
echo

echo "Name: POSTGRES_DB"
echo "Value: roda_analytics"
echo

echo "Name: CRIME_DATA_URL"
echo "Value: https://datosabiertos.bogota.gov.co/dataset/7b270013-42ca-436b-9c1e-3bcb7d280c6b/resource/b24e6cfa-ae5d-465c-8fe7-e494cd377897/download/dai_gpkg.zip"
echo

# ====================================
# 🧹 5. CLEANUP
# ====================================
echo
echo "🧹 5. Limpieza..."
echo "📁 Archivo de clave guardado como: $KEY_FILE"
echo "⚠️  IMPORTANTE: Borra este archivo después de configurar GitHub:"
echo "   rm $KEY_FILE"
echo

# ====================================
# 📝 6. PASOS SIGUIENTES
# ====================================
echo "📝 PASOS SIGUIENTES:"
echo "==================="
echo "1. 🔑 Configurar todos los secrets en GitHub (mostrados arriba)"
echo "2. 🗑️  Borrar el archivo de clave: rm $KEY_FILE"
echo "3. 🚀 Hacer commit y push para activar el pipeline"
echo "4. 🔍 Verificar en: https://github.com/JuanHoKKeR/Prueba_Tecnica_ETL/actions"
echo
echo "✅ Configuración de GitHub Actions completada!"
