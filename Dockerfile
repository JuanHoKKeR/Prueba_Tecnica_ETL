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
    && rm -rf /var/lib/apt/lists/*

# Configuramos variables de entorno para GDAL
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Copiamos primero el archivo de requisitos para aprovechar el cache de Docker
COPY requirements.txt .

# Instalamos las dependencias de Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiamos el codigo de la aplicacion
COPY src/ ./src/
COPY sql/ ./sql/

# Creamos un directorio para el cache
RUN mkdir -p /tmp/roda_cache

# Creamos un usuario no-root por seguridad
RUN useradd -m -u 1000 roda && \
    chown -R roda:roda /app /tmp/roda_cache

# Cambiamos al usuario no-root
USER roda

# Exponemos el puerto 8080 para la aplicacion
EXPOSE 8080

# Configuramos un health check para verificar que la app este corriendo
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# Comando para ejecutar la aplicacion con uvicorn
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]