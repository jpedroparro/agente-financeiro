from datetime import date

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CommandHandler,
    filters,
)

from .. import db
from ..calculations import MODOS, formatar_plano, simular_plano_mensal

ESCOLHER_OBJETIVO, ESCOLHER_MODO = range(300, 302)

MODO_KEYBOARD = ReplyKeyboardMarkup(
    [[MODOS[m]["label"] for m in MODOS]], one_time_keyboard=True, resize_keyboard=True
)


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


def _modo_por_texto(texto: str):
    texto = texto.strip().lower()
    return next((m for m in MODOS if MODOS[m]["label"].lower() == texto or m == texto), None)


async def modo_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    if not db.usuario_existe(chat_id):
        await update.effective_message.reply_text("Você ainda não fez seu cadastro. Use /start.")
        return ConversationHandler.END

    objetivos = db.objetivos_ativos(chat_id)
    if not objetivos:
        await update.effective_message.reply_text("Você não tem nenhum objetivo ativo. Use /objetivo para criar um.")
        return ConversationHandler.END

    if len(objetivos) == 1:
        context.user_data["modo_objetivo_id"] = objetivos[0]["id"]
        context.user_data["modo_objetivo_nome"] = objetivos[0]["nome"]
        await update.effective_message.reply_text(
            f"Qual o novo modo pra \"{objetivos[0]['nome']}\"?", reply_markup=MODO_KEYBOARD
        )
        return ESCOLHER_MODO

    context.user_data["objetivos_disponiveis"] = objetivos
    await update.effective_message.reply_text(
        "De qual objetivo você quer trocar o modo?", reply_markup=_teclado_objetivos(objetivos)
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

    context.user_data["modo_objetivo_id"] = obj["id"]
    context.user_data["modo_objetivo_nome"] = obj["nome"]
    await update.effective_message.reply_text(
        f"Qual o novo modo pra \"{obj['nome']}\"?", reply_markup=MODO_KEYBOARD
    )
    return ESCOLHER_MODO


async def escolher_modo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    modo = _modo_por_texto(update.effective_message.text)
    if modo is None:
        await update.effective_message.reply_text("Escolha um dos modos disponíveis.", reply_markup=MODO_KEYBOARD)
        return ESCOLHER_MODO

    objetivo_id = context.user_data["modo_objetivo_id"]
    nome = context.user_data["modo_objetivo_nome"]
    db.atualizar_modo(objetivo_id, modo)

    obj = db.objetivo_por_id(objetivo_id)
    chat_id = update.effective_chat.id
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
        f"Modo de \"{nome}\" atualizado para {MODOS[modo]['label']}! ✅\n\n"
        + formatar_plano(plano, obj["modo"], obj["nome"]),
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancelar_modo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("Troca de modo cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


modo_conv = ConversationHandler(
    entry_points=[CommandHandler("modo", modo_start)],
    states={
        ESCOLHER_OBJETIVO: [MessageHandler(filters.TEXT & ~filters.COMMAND, escolher_objetivo)],
        ESCOLHER_MODO: [MessageHandler(filters.TEXT & ~filters.COMMAND, escolher_modo)],
    },
    fallbacks=[CommandHandler("cancelar", cancelar_modo)],
    conversation_timeout=900,
)
