# Imagen del bot en etapas:
#   base: lo común (sistema, dependencias de la aplicación y código)
#   dev:  base + herramientas de prueba (requirements-dev.txt); la usa el servicio `tests`
#   prod: base sin herramientas de prueba; es la última etapa, así que se construye por defecto

# Imagen de Python
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalación de dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Archivo de dependencias
COPY requirements.txt .

# Instala librerias de requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copia codigo fuente
COPY . .

# Etapa de desarrollo: añade pytest y compañía
FROM base AS dev

RUN pip install --no-cache-dir -r requirements-dev.txt

# Etapa de producción (debe ser la última del archivo)
FROM base AS prod

# Comando por defecto
CMD ["python", "bot/main.py"]
