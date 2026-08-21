from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CommandHandler,
    filters,
)

from .. import db
from ..calculations import formatar_plano, parse_valor, simular_plano_mensal
from datetime import date

ESCOLHER_OBJETIVO, VALOR_APORTE = range(200, 202)


def _teclado_objetivos(objetivos):
    return ReplyKeyboardMarkup(
        [[f"{o['nome']} (#{o['id']})"] for o in objetivos],
        one_time_keyboard=True,
        resize_keyboard=True,
    )


def _objetivo_por_label(objetivos, texto: str):
    texto = texto.strip()
    for o in objetivos:
        if texto == f"{o['nome']} (#{o['id']})":
            return o
    return None


async def aporte_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    if not db.usuario_existe(chat_id):
        await update.effective_message.reply_text("Você ainda não fez seu cadastro. Use /start.")
        return ConversationHandler.END

    objetivos = db.objetivos_ativos(chat_id)
    if not objetivos:
        await update.effective_message.reply_text("Você não tem nenhum objetivo ativo. Use /objetivo para criar um.")
        return ConversationHandler.END

    if len(objetivos) == 1:
        context.user_data["aporte_objetivo_id"] = objetivos[0]["id"]
        context.user_data["aporte_objetivo_nome"] = objetivos[0]["nome"]
        await update.effective_message.reply_text(
            f"Quanto você guardou pro objetivo \"{objetivos[0]['nome']}\" este mês?",
            reply_markup=ReplyKeyboardRemove(),
        )
        return VALOR_APORTE

    context.user_data["objetivos_disponiveis"] = objetivos
    await update.effective_message.reply_text(
        "Pra qual objetivo é esse aporte?", reply_markup=_teclado_objetivos(objetivos)
    )
    return ESCOLHER_OBJETIVO


async def escolher_objetivo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    objetivos = context.user_data.get("objetivos_disponiveis", [])
    obj = _objetivo_por_label(objetivos, update.effective_message.text)
    if obj is None:
        await update.effective_message.reply_text(
            "Escolha um dos objetivos listados.", reply_markup=_teclado_objetivos(objetivos)
        )
        return ESCOLHER_OBJETIVO

    context.user_data["aporte_objetivo_id"] = obj["id"]
    context.user_data["aporte_objetivo_nome"] = obj["nome"]
    await update.effective_message.reply_text(
        f"Quanto você guardou pro objetivo \"{obj['nome']}\" este mês?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return VALOR_APORTE


async def receber_valor_aporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        valor = parse_valor(update.effective_message.text)
    except ValueError:
        await update.effective_message.reply_text("Não entendi o valor. Digite apenas números, ex: 500")
        return VALOR_APORTE

    objetivo_id = context.user_data["aporte_objetivo_id"]
    nome = context.user_data["aporte_objetivo_nome"]
    chat_id = update.effective_chat.id

    resultado = db.registrar_aporte(objetivo_id, chat_id, valor)

    if resultado and resultado["valor_atual"] >= resultado["valor_alvo"]:
        await update.effective_message.reply_text(
            f"🎉 Parabéns! Você atingiu o objetivo \"{nome}\"! "
            f"Total guardado: R$ {resultado['valor_atual']:,.2f}"
        )
        context.user_data.clear()
        return ConversationHandler.END

    obj = db.objetivo_por_id(objetivo_id)
    renda_total = db.total_entradas(chat_id)
    despesas = db.total_despesas(chat_id)
    parcelas = db.parcelas_por_mes(chat_id)
    data_alvo = date.fromisoformat(obj["data_alvo"])
    plano = simular_plano_mensal(
        renda_total=renda_total,
        despesas_fixas=despesas,
        valor_atual=obj["valor_atual"],
        valor_alvo=obj["valor_alvo"],
        data_alvo=data_alvo,
        modo=obj["modo"],
        parcelas_por_mes=parcelas,
    )
    await update.effective_message.reply_text(
        f"Aporte de R$ {valor:,.2f} registrado em \"{nome}\"! ✅\n\n" + formatar_plano(plano, obj["modo"], obj["nome"]),
        parse_mode="Markdown",
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancelar_aporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("Registro de aporte cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


aporte_conv = ConversationHandler(
    entry_points=[CommandHandler("aporte", aporte_start)],
    states={
        ESCOLHER_OBJETIVO: [MessageHandler(filters.TEXT & ~filters.COMMAND, escolher_objetivo)],
        VALOR_APORTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor_aporte)],
    },
    fallbacks=[CommandHandler("cancelar", cancelar_aporte)],
    conversation_timeout=900,
)
