# 🚀 Deploy Scripts - RODA Analytics

Este directorio contiene scripts de deployment y configuración para RODA Analytics en Google Cloud Platform.

## 📋 Archivos Disponibles

### 🔧 Scripts de Configuración
- `setup-bigquery.sh` - Configurar BigQuery para analytics
- `setup-scheduler.sh` - Configurar Cloud Scheduler para actualizaciones automáticas
- `setup-schema.sh` - Configurar PostGIS y schema de base de datos
- `create-cloud-sql.sh` - Crear instancia Cloud SQL

### 🚀 Scripts de Deployment  
- `deploy-cloud-run.sh` - Desplegar aplicación a Cloud Run
- `setup-github-actions.template.sh` - Template para configurar CI/CD

### 📄 Archivos de Configuración
- `cloud-run-env.txt` - Template de variables de entorno

## 🔐 Configuración Segura

### 1. Configurar Variables de Entorno

Crear archivo `.env` en la raíz del proyecto:

```bash
# Copiar desde cloud-run-env.txt y completar valores
cp deploy/cloud-run-env.txt .env
# Editar .env con tus valores reales
```

### 2. Configurar Scripts Locales

```bash
# Crear copia local del template de GitHub Actions
cp deploy/setup-github-actions.template.sh deploy/setup-github-sa.sh
# Editar setup-github-sa.sh con tus valores
```

### 3. Cargar Variables

```bash
# Cargar variables antes de ejecutar scripts
source .env
```

## 🚀 Flujo de Deployment

### Setup Inicial (una vez)

```bash
# 1. Configurar variables
source .env

# 2. Crear Cloud SQL (si no existe)
./deploy/create-cloud-sql.sh

# 3. Configurar schema
./deploy/setup-schema.sh

# 4. Configurar BigQuery
./deploy/setup-bigquery.sh

# 5. Configurar Scheduler
./deploy/setup-scheduler.sh

# 6. Configurar GitHub Actions
./deploy/setup-github-sa.sh
```

### Deployment Regular

```bash
# Opción A: Manual
source .env && ./deploy/deploy-cloud-run.sh

# Opción B: Automático vía GitHub Actions
git push origin main
```

## 🔒 Seguridad

- ✅ **Nunca commitear** archivos `.env` o con datos reales
- ✅ **Usar templates** para scripts compartidos
- ✅ **Variables de entorno** para valores sensibles
- ✅ **Service accounts** con permisos mínimos
- ✅ **GitHub Environments** para secrets de CI/CD

## 📚 Variables Requeridas

```bash
# Google Cloud
GCP_PROJECT_ID=your-project-id
GCP_REGION=us-central1

# Base de datos
DATABASE_URL=postgresql://user:pass@host:5432/db
POSTGRES_HOST=your-cloud-sql-ip
POSTGRES_USER=your-db-user
POSTGRES_PASSWORD=your-db-password
POSTGRES_DB=your-database-name

# Datos
CRIME_DATA_URL=your-crime-data-source

# GitHub (para setup-github-sa.sh)
GITHUB_REPO_OWNER=your-username
GITHUB_REPO_NAME=your-repo-name
```

## 🆘 Troubleshooting

### Error de permisos
```bash
# Verificar roles del service account
gcloud projects get-iam-policy $GCP_PROJECT_ID

# Re-ejecutar setup si es necesario
./deploy/setup-github-sa.sh
```

### Variables no definidas
```bash
# Verificar que .env está cargado
echo $GCP_PROJECT_ID

# Cargar variables
source .env
```

### Deployment falla
```bash
# Verificar logs
gcloud run services logs read roda-analytics --region=$GCP_REGION

# Verificar imagen
gcloud container images list --repository=us-central1-docker.pkg.dev/$GCP_PROJECT_ID/roda-repo
```
