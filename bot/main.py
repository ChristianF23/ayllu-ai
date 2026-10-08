import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from agents.orchestrator import orchestrator
from utils.database import init_db_pool, close_db_pool, is_user_allowed
from utils.cost_tracker import log_cost

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("AylluBot")

async def reply_safe(message, text: str):
    """
    Responde con Markdown; si Telegram lo rechaza (entidades mal formadas),
    reintenta en texto plano para no perder el mensaje.
    """
    try:
        await message.reply_text(text, parse_mode="Markdown")
    except BadRequest as e:
        logger.warning(f"⚠️ Telegram rechazó el Markdown ({e}); reenviando como texto plano.")
        await message.reply_text(text)

async def post_init(application):
    """
    Hook de inicio de python-telegram-bot: inicializa el pool de PostgreSQL.
    """
    from utils.okf_reader import okf_reader

    logger.info("Inicializando conexión con PostgreSQL...")
    await init_db_pool()

    # Carga de conceptos OKF
    okf_reader.load_bundle()

async def post_shutdown(application):
    """
    Hook de apagado: cierra las conexiones de la BD limpiamente.
    """
    logger.info("Cerrando conexión con PostgreSQL...")
    await close_db_pool()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Validar seguridad contra PostgreSQL
    if not await is_user_allowed(user_id):
        logger.warning(f"⛔ Acceso denegado en /start para ID no autorizado: {user_id}")
        await reply_safe(update.message, "⛔ *Acceso denegado:* No estás en la lista de usuarios autorizados.")
        return

    welcome_text = (
        "🤖 **¡Hola! Bienvenido al Ecosistema Ayllu AI.**\n\n"
        "Soy el Agente Orquestador. Puedes enviarme cualquier consulta o mensaje "
        "y me encargaré de procesarlo con nuestros modelos de IA.\n\n"
        "Escribe un mensaje para comenzar."
    )
    await reply_safe(update.message, welcome_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Usuario"

    # 🔒 Capa de Seguridad: Validar lista blanca en la BD
    if not await is_user_allowed(user_id):
        logger.warning(f"⛔ Intento de acceso no autorizado detectado de @{username} (ID: {user_id})")
        await reply_safe(
            update.message,
            "⛔ *Acceso denegado:* Tu ID de Telegram no está autorizado para interactuar con este bot."
        )
        return

    user_text = update.message.text
    logger.info(f"Mensaje autorizado de @{username} ({user_id}): {user_text}")

    await update.message.chat.send_action(action="typing")

    # Invocar al Orquestador
    result = await orchestrator.process_request(user_prompt=user_text)

    if result["status"] == "success":
        response_text = result["response"]
        tokens_prompt = result["usage"]["prompt_tokens"]
        tokens_completion = result["usage"]["completion_tokens"]
        tokens_total = result["usage"]["total_tokens"]
        cost = result["usage"]["estimated_cost_usd"] or 0.0
        model_used = result["model_used"]

        # Registramos la métrica de consumo en PostgreSQL
        await log_cost(
            user_id=user_id,
            model_used=model_used,
            prompt_tokens=tokens_prompt,
            completion_tokens=tokens_completion,
            estimated_cost_usd=cost,
            agent_id="orchestrator"
        )

        reply_message = (
            f"{response_text}\n\n"
            f"───────────────\n"
            f"📊 *Modelo:* `{model_used}` | *Tokens:* `{tokens_total}` | *Costo est.:* `${cost:.6f}`"
        )
        await reply_safe(update.message, reply_message)
    else:
        error_msg = f"❌ Ocurrió un error al procesar tu mensaje: {result['message']}"
        await update.message.reply_text(error_msg)

def main():
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not telegram_token or not openai_key:
        logger.error("⚠️ Faltan credenciales en el archivo .env.")
        return

    logger.info("=== Iniciando Ayllu AI (Conexión asíncrona a BD activa) ===")
    
    app = (
        ApplicationBuilder()
        .token(telegram_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot escuchando eventos en Telegram...")
    app.run_polling()

if __name__ == "__main__":
    main()