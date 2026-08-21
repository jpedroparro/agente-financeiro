import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes

from bot import db
from bot.handlers.aporte import aporte_conv
from bot.handlers.ajuda import ajuda_handler
from bot.handlers.cadastro import cadastro_conv
from bot.handlers.editar import editar_conv
from bot.handlers.fatura import fatura_conv
from bot.handlers.lembrete import agendar_lembretes
from bot.handlers.modo import modo_conv
from bot.handlers.objetivo import objetivo_conv, status_handler
from bot.handlers.parcelas import parcelas_handler
from bot.handlers.perfil import perfil_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Erro ao processar update: %s", update, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Ops, algo deu errado por aqui. Tente novamente ou use /cancelar."
            )
        except Exception:
            logger.exception("Falha ao notificar usuário sobre o erro")


def main():
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Defina TELEGRAM_BOT_TOKEN no arquivo .env")

    db.init_db()

    app = ApplicationBuilder().token(token).build()

    app.add_handler(cadastro_conv)
    app.add_handler(objetivo_conv)
    app.add_handler(aporte_conv)
    app.add_handler(modo_conv)
    app.add_handler(editar_conv)
    app.add_handler(fatura_conv)
    app.add_handler(parcelas_handler)
    app.add_handler(status_handler)
    app.add_handler(perfil_handler)
    app.add_handler(ajuda_handler)
    app.add_error_handler(error_handler)

    agendar_lembretes(app.job_queue)

    app.run_polling()


if __name__ == "__main__":
    main()
