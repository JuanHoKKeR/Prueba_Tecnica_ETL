# Usamos la imagen base de Python 3.11 slim para ahorrar espacio
FROM python:3.11-slim

# Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instalamos dependencias del sistema necesarias para PostGIS y librerias geoespaciales
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Configuramos variables de entorno para GDAL y producción
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080

# Copiamos primero el archivo de requisitos para aprovechar el cache de Docker
COPY requirements.txt .

# Instalamos las dependencias de Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiamos el codigo de la aplicacion
COPY src/ ./src/
COPY sql/ ./sql/

# Creamos directorios necesarios
RUN mkdir -p /tmp/roda_cache /app/logs

# Creamos un usuario no-root por seguridad (Cloud Run requirement)
RUN useradd -m -u 1000 roda && \
    chown -R roda:roda /app /tmp/roda_cache

# Cambiamos al usuario no-root
USER roda

# Exponemos el puerto 8080 para Cloud Run
EXPOSE 8080

# Health check optimizado para Cloud Run (simple HTTP check)
HEALTHCHECK --interval=60s --timeout=30s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Comando optimizado para Cloud Run con manejo de señales
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--access-log"]