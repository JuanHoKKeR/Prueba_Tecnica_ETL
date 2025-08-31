# 🚀 GitHub Actions CI/CD Setup

Este documento explica cómo configurar GitHub Actions para automatizar completamente el deployment de RODA Analytics.

## 🎯 ¿Qué automatiza el pipeline?

✅ **Build de Docker images** con versionado automático  
✅ **Push a Artifact Registry** de Google Cloud  
✅ **Deploy automático a Cloud Run** con secrets seguros  
✅ **Health checks** post-deployment contra el servicio real  
✅ **Trigger de ETL pipeline** después del deploy  
✅ **Notificaciones** de estado y métricas  

## 🌍 Configuración con GitHub Environments

**¿Por qué usar Environments en lugar de solo Secrets?**
- ✅ **Separación clara** entre dev/staging/production
- ✅ **Reglas de protección** (requiere approval para prod)
- ✅ **Variables específicas** por environment
- ✅ **Mejor seguridad** y trazabilidad

### 1. Crear Environment "production"

1. Ve a: [Repository Settings > Environments](https://github.com/JuanHoKKeR/Prueba_Tecnica_ETL/settings/environments)
2. Click **"New environment"**
3. Nombre: `production`

### 2. Configurar Environment Variables y Secrets

En el environment **"production"**, se apreciaran:

#### 🔐 Environment Secrets:
```
GCP_SERVICE_ACCOUNT_KEY = [JSON key del service account]
DATABASE_URL = 
POSTGRES_HOST = 
POSTGRES_PORT = 
POSTGRES_USER = 
POSTGRES_PASSWORD = 
POSTGRES_DB = 
CRIME_DATA_URL = 
```

#### 🌐 Environment Variables (no secretas):
```
SERVICE_DOMAIN = roda-analytics-jebcgzfxdq-uc.a.run.app
API_ENV = production
LOG_LEVEL = INFO
```


## 🌐 Cambiar URL del Servicio

**Slo cambiar en un lugar:**

1. En el archivo `.github/workflows/ci-cd.yml`:
```yaml
env:
  # ... otras variables ...
  SERVICE_DOMAIN: nuevo-dominio.com  # ← Solo cambiar aquí
```

2. O en Environment Variables del environment "production":
```
SERVICE_DOMAIN = nuevo-dominio.com
```

**Todo el pipeline se actualizará automáticamente** 🎯

### 3. Activar el pipeline

```bash
git add .
git commit -m "🚀 Setup GitHub Actions CI/CD pipeline"
git push origin main
```

## 🔄 Workflow del Pipeline

### **Trigger Conditions:**
- ✅ Push a `main` → Deploy automático
- ✅ Push a `develop` → Solo testing
- ✅ Pull Request → Testing + preview


## 🔍 Monitoring

### **GitHub Actions UI:**
- 📊 Status de todos los workflows
- 📝 Logs detallados de cada step
- 📈 Métricas de tiempo de build/deploy
- 🔔 Notificaciones de fallos

### **Verificación post-deploy:**
```bash
# Health check automático
curl https://roda-analytics-jebcgzfxdq-uc.a.run.app/health

# Trigger ETL automático
curl -X POST https://roda-analytics-jebcgzfxdq-uc.a.run.app/process
```

## 🎯 Quick Commands

```bash
# Ver status del último deployment
gh run list --repo JuanHoKKeR/Prueba_Tecnica_ETL

# Trigger manual deployment
gh workflow run ci-cd.yml --repo JuanHoKKeR/Prueba_Tecnica_ETL

# Ver logs del deployment
gh run view --repo JuanHoKKeR/Prueba_Tecnica_ETL
```

---