# Imagen de Python
FROM python:3.11-slim

ENV PYTHONBUFFERED=1

WORKDIR /app

# Instalación de dependencias
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt-get/lists/*

# Archivo de dependencias
COPY requirements.txt .

# Instala librerias de requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copia codigo fuente

COPY . .

# Comando por defecto
CMD ["python", "bot/main.py"]