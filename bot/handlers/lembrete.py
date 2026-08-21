import logging
from datetime import time

from telegram.ext import ContextTypes

from .. import db
from ..calculations import formatar_plano

logger = logging.getLogger(__name__)

DIA_DO_LEMBRETE = 1
HORA_DO_LEMBRETE = time(hour=9, minute=0)


async def enviar_lembretes_mensais(context: ContextTypes.DEFAULT_TYPE):
    from datetime import date

    from .objetivo import calcular_planos_todos

    if date.today().day != DIA_DO_LEMBRETE:
        return

    usuarios = db.usuarios_com_objetivos_ativos()
    for row in usuarios:
        chat_id = row["chat_id"]
        resultados = calcular_planos_todos(chat_id)
        if not resultados:
            continue
        try:
            await context.bot.send_message(
                chat_id, "🔔 Lembrete mensal: hora de fazer os aportes do mês!"
            )
            for obj, plano in resultados:
                texto = formatar_plano(plano, obj["modo"], obj["nome"])
                await context.bot.send_message(chat_id, texto, parse_mode="Markdown")
        except Exception:
            logger.exception("Falha ao enviar lembrete para chat_id=%s", chat_id)


def agendar_lembretes(job_queue):
    job_queue.run_daily(
        enviar_lembretes_mensais,
        time=HORA_DO_LEMBRETE,
        name="lembrete_mensal",
    )
