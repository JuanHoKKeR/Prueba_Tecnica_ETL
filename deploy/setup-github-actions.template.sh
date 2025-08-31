#!/bin/bash
# 🔧 Setup GitHub Actions para RODA Analytics - TEMPLATE
# Copiar este archivo y reemplazar las variables con tus valores reales

set -e

# ====================================
# 🔧 CONFIGURACIÓN - ACTUALIZAR ESTOS VALORES
# ====================================
PROJECT_ID="${GCP_PROJECT_ID:-YOUR_PROJECT_ID}"
SERVICE_ACCOUNT_NAME="${GITHUB_SA_NAME:-github-actions-sa}"
REPO_OWNER="${GITHUB_REPO_OWNER:-YOUR_GITHUB_USERNAME}"
REPO_NAME="${GITHUB_REPO_NAME:-YOUR_REPO_NAME}"

SERVICE_ACCOUNT_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"

echo "🔧 Configurando GitHub Actions para RODA Analytics..."
echo "=================================================="
echo "📋 Configuración:"
echo "   Project ID: $PROJECT_ID"
echo "   Service Account: $SERVICE_ACCOUNT_EMAIL"
echo "   Repository: $REPO_OWNER/$REPO_NAME"
echo

# ====================================
# 🔐 1. CREAR SERVICE ACCOUNT
# ====================================
echo "🔐 1. Creando Service Account..."

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
# 🎯 2. ASIGNAR ROLES
# ====================================
echo "🎯 2. Asignando roles necesarios..."

ROLES=(
    "roles/run.admin"
    "roles/storage.admin"
    "roles/iam.serviceAccountUser"
    "roles/cloudsql.client"
    "roles/bigquery.dataEditor"
    "roles/bigquery.jobUser"
    "roles/cloudscheduler.admin"
)

for role in "${ROLES[@]}"; do
    echo "📝 Asignando: $role"
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
        --role="$role" \
        --quiet
done

# ====================================
# 🗝️ 3. GENERAR CLAVE (MÉTODO SEGURO)
# ====================================
echo "🗝️ 3. Generando clave JSON..."

KEY_FILE="github-actions-key-$(date +%Y%m%d-%H%M%S).json"
gcloud iam service-accounts keys create $KEY_FILE \
    --iam-account=$SERVICE_ACCOUNT_EMAIL \
    --project=$PROJECT_ID

echo "✅ Clave generada: $KEY_FILE"

# ====================================
# 📋 4. INSTRUCCIONES SEGURAS
# ====================================
echo
echo "📋 CONFIGURACIÓN EN GITHUB:"
echo "============================"
echo
echo "1. 🌍 Ve a GitHub Environments:"
echo "   https://github.com/$REPO_OWNER/$REPO_NAME/settings/environments"
echo
echo "2. 🆕 Crear environment 'production'"
echo
echo "3. 📄 Copiar contenido del archivo JSON:"
echo "   cat $KEY_FILE"
echo
echo "4. 📋 Configurar estos Environment Secrets:"
echo
cat << EOF
GCP_SERVICE_ACCOUNT_KEY=[contenido del JSON generado arriba]
DATABASE_URL=\${DATABASE_URL}
POSTGRES_HOST=\${POSTGRES_HOST}
POSTGRES_PORT=\${POSTGRES_PORT}
POSTGRES_USER=\${POSTGRES_USER}
POSTGRES_PASSWORD=\${POSTGRES_PASSWORD}
POSTGRES_DB=\${POSTGRES_DB}
CRIME_DATA_URL=\${CRIME_DATA_URL}
EOF
echo
echo "5. 🗑️ Borrar archivo local DESPUÉS de configurar GitHub:"
echo "   rm $KEY_FILE"
echo
echo "✅ Service Account configurado!"
echo "🔄 Siguiente: Configurar environment secrets en GitHub"
echo "📋 URL: https://github.com/$REPO_OWNER/$REPO_NAME/settings/environments"
