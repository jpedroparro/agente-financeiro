from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CommandHandler,
    filters,
)

from .. import db

TIPO, ITEM = range(400, 402)

TIPO_KEYBOARD = ReplyKeyboardMarkup(
    [["Entrada", "Despesa"]], one_time_keyboard=True, resize_keyboard=True
)


def _teclado_itens(itens):
    linhas = [[f"{i['descricao']} (#{i['id']}) - R$ {i['valor']:,.2f}"] for i in itens]
    linhas.append(["Cancelar"])
    return ReplyKeyboardMarkup(linhas, one_time_keyboard=True, resize_keyboard=True)


def _item_por_label(itens, texto: str):
    texto = texto.strip()
    for i in itens:
        if texto.startswith(f"{i['descricao']} (#{i['id']})"):
            return i
    return None


async def editar_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    if not db.usuario_existe(chat_id):
        await update.effective_message.reply_text("Você ainda não fez seu cadastro. Use /start.")
        return ConversationHandler.END

    context.user_data.clear()
    await update.effective_message.reply_text(
        "O que você quer remover: uma entrada ou uma despesa?",
        reply_markup=TIPO_KEYBOARD,
    )
    return TIPO


async def escolher_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    resposta = update.effective_message.text.strip().lower()
    chat_id = update.effective_chat.id

    if resposta.startswith("entrada"):
        itens = db.listar_entradas(chat_id)
        tipo = "entrada"
    elif resposta.startswith("despesa"):
        itens = db.listar_despesas(chat_id)
        tipo = "despesa"
    else:
        await update.effective_message.reply_text("Escolha 'Entrada' ou 'Despesa'.", reply_markup=TIPO_KEYBOARD)
        return TIPO

    if not itens:
        await update.effective_message.reply_text(
            f"Você não tem nenhuma {tipo} cadastrada.", reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data["editar_tipo"] = tipo
    context.user_data["editar_itens"] = itens
    await update.effective_message.reply_text(
        f"Qual {tipo} você quer remover?", reply_markup=_teclado_itens(itens)
    )
    return ITEM


async def remover_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.effective_message.text.strip()
    if texto.lower() == "cancelar":
        return await cancelar_edicao(update, context)

    itens = context.user_data.get("editar_itens", [])
    item = _item_por_label(itens, texto)
    if item is None:
        await update.effective_message.reply_text("Escolha um dos itens listados.", reply_markup=_teclado_itens(itens))
        return ITEM

    chat_id = update.effective_chat.id
    tipo = context.user_data["editar_tipo"]
    if tipo == "entrada":
        db.remover_entrada(chat_id, item["id"])
    else:
        db.remover_despesa(chat_id, item["id"])

    await update.effective_message.reply_text(
        f"Removido: {item['descricao']} (R$ {item['valor']:,.2f}). ✅",
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancelar_edicao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("Edição cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


editar_conv = ConversationHandler(
    entry_points=[CommandHandler("editar", editar_start)],
    states={
        TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, escolher_tipo)],
        ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, remover_item)],
    },
    fallbacks=[CommandHandler("cancelar", cancelar_edicao)],
    conversation_timeout=900,
)
