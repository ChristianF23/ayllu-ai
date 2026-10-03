import os
import time
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def main():
    print("=== Iniciando Ayllu AI")

    openai_key = os.getenv("OPENAI_API_KEY")
    telegram_token = os.getenv("TELEGRAM_TOKEN")

    if openai_key and telegram_token:
        print("Variables de entorno cargadas correctamente", flush=True)
    else:
        print("Advertencia: Revise el archivo .env, faltan credenciales", flush=True)

    print("Esperando conexión de agentes...", flush=True)

    # Bucle para mantener contenedor activo
    while True:
        time.sleep(10)

if __name__ == "__main__":
    main()