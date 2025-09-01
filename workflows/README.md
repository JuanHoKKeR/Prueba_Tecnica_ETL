# Google Cloud Workflows - ETL Automation

Este directorio contiene los workflows de Google Cloud para automatizar el procesamiento ETL de RODA Analytics.

## 📁 Archivos

### `etl-simple.yaml`
Workflow simplificado y operativo para producción.

**Funciones:**
- ✅ Health check del servicio Cloud Run
- ✅ Trigger del proceso ETL 
- ✅ Monitoreo de progreso
- ✅ Logging de resultados

**Estado:** 🟢 **ACTIVO** - Desplegado como `roda-etl-simple`

### `etl-orchestration.yaml` 
Workflow complejo con funciones avanzadas (desarrollo).

**Funciones:**
- 🔄 Procesamiento paralelo por zonas
- 🔄 Validación avanzada de BigQuery
- 🔄 Manejo de errores robusto
- 🔄 Reportes detallados

**Estado:** 🟡 **EN DESARROLLO** - Tiene problemas de sintaxis

## 🚀 Despliegue Rápido

```bash
# Desplegar workflow activo
gcloud workflows deploy roda-etl-simple \
  --source=workflows/etl-simple.yaml \
  --location=us-central1

# Ejecutar manualmente
gcloud workflows execute roda-etl-simple \
  --location=us-central1
```

## 📊 Estado Actual

| Workflow | Estado | Última Ejecución | Resultado |
|----------|--------|------------------|-----------|
| `roda-etl-simple` | 🟢 Activo | 2025-09-01 06:13 | ✅ SUCCESS |
| `roda-etl-orchestration` | 🔴 Inactivo | - | ❌ Syntax Error |

## 📋 Próximos Pasos

1. **Corregir sintaxis** en `etl-orchestration.yaml`
2. **Probar funciones avanzadas** de procesamiento paralelo
3. **Migrar** de simple a orchestration cuando esté listo
4. **Integrar ML endpoints** en workflows para análisis automático
5. **Agregar workflows** para análisis específicos

### 🤖 Integración ML (NUEVO)
Los workflows ahora pueden integrar análisis ML automático:

```yaml
# Ejemplo: Añadir análisis ML al workflow ETL
- mlAnalysis:
    call: http.get
    args:
      url: ${cloud_run_url + "/ml/insights"}
    result: ml_insights

- evaluateAnomalies:
    switch:
      - condition: ${ml_insights.body.insights[0].type == "ANOMALY"}
        next: alertManagement
      - condition: true
        next: continueProcessing
```

## 🔗 Enlaces Útiles

- [Documentación Completa](../docs/WORKFLOWS_GUIDE.md)
- [Google Cloud Workflows Console](https://console.cloud.google.com/workflows)
- [Cloud Scheduler Jobs](https://console.cloud.google.com/cloudscheduler)
