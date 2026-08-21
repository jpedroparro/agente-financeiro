from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CommandHandler,
    filters,
)

from .. import db
from ..calculations import parse_valor

(
    NOME,
    RENDA,
    OUTRA_ENTRADA_PERGUNTA,
    OUTRA_ENTRADA_DESC,
    OUTRA_ENTRADA_VALOR,
    DESPESA_PERGUNTA,
    DESPESA_DESC,
    DESPESA_VALOR,
    GASTOS_VARIAVEIS,
) = range(9)

SIM_NAO = ReplyKeyboardMarkup([["Sim", "Não"]], one_time_keyboard=True, resize_keyboard=True)


async def cadastro_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text(
        "Vamos montar seu perfil financeiro. Qual é o seu nome?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return NOME


async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["nome"] = update.effective_message.text.strip()
    await update.effective_message.reply_text(
        "Qual é a sua renda principal mensal (ex: salário)? Digite só o número."
    )
    return RENDA


async def receber_renda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        valor = parse_valor(update.effective_message.text)
    except ValueError:
        await update.effective_message.reply_text("Não entendi o valor. Digite apenas números, ex: 3500")
        return RENDA
    context.user_data["entradas"] = [("Renda principal", valor)]
    await update.effective_message.reply_text(
        "Você tem outras entradas (freelance, benefícios, etc.)?", reply_markup=SIM_NAO
    )
    return OUTRA_ENTRADA_PERGUNTA


async def outra_entrada_pergunta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    resposta = update.effective_message.text.strip().lower()
    if resposta.startswith("s"):
        await update.effective_message.reply_text(
            "Qual é a descrição dessa entrada?", reply_markup=ReplyKeyboardRemove()
        )
        return OUTRA_ENTRADA_DESC
    return await iniciar_despesas(update, context)


async def outra_entrada_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["_desc_temp"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("Qual é o valor mensal dessa entrada?")
    return OUTRA_ENTRADA_VALOR


async def outra_entrada_valor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        valor = parse_valor(update.effective_message.text)
    except ValueError:
        await update.effective_message.reply_text("Não entendi o valor. Digite apenas números, ex: 500")
        return OUTRA_ENTRADA_VALOR
    desc = context.user_data.pop("_desc_temp")
    context.user_data["entradas"].append((desc, valor))
    await update.effective_message.reply_text("Mais alguma entrada?", reply_markup=SIM_NAO)
    return OUTRA_ENTRADA_PERGUNTA


async def iniciar_despesas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault("despesas", [])
    await update.effective_message.reply_text(
        "Agora as contas fixas. Você tem alguma despesa fixa pra registrar "
        "(aluguel, financiamento, cartão, assinaturas)?",
        reply_markup=SIM_NAO,
    )
    return DESPESA_PERGUNTA


async def despesa_pergunta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    resposta = update.effective_message.text.strip().lower()
    if resposta.startswith("s"):
        await update.effective_message.reply_text(
            "Qual é a descrição dessa despesa?", reply_markup=ReplyKeyboardRemove()
        )
        return DESPESA_DESC
    return await pedir_gastos_variaveis(update, context)


async def despesa_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["_desc_temp"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("Qual é o valor mensal dessa despesa?")
    return DESPESA_VALOR


async def despesa_valor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        valor = parse_valor(update.effective_message.text)
    except ValueError:
        await update.effective_message.reply_text("Não entendi o valor. Digite apenas números, ex: 1200")
        return DESPESA_VALOR
    desc = context.user_data.pop("_desc_temp")
    context.user_data["despesas"].append((desc, valor))
    await update.effective_message.reply_text("Mais alguma despesa fixa?", reply_markup=SIM_NAO)
    return DESPESA_PERGUNTA


async def pedir_gastos_variaveis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Por último: qual sua estimativa de gastos variáveis por mês "
        "(mercado, transporte, lazer)? Se não quiser informar, digite 0.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return GASTOS_VARIAVEIS


async def receber_gastos_variaveis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        valor = parse_valor(update.effective_message.text)
    except ValueError:
        await update.effective_message.reply_text("Não entendi o valor. Digite apenas números, ex: 800")
        return GASTOS_VARIAVEIS
    context.user_data["gastos_variaveis"] = valor
    return await finalizar_cadastro(update, context)


async def finalizar_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    nome = context.user_data["nome"]

    db.upsert_usuario(chat_id, nome)
    db.limpar_entradas_despesas(chat_id)
    for desc, valor in context.user_data.get("entradas", []):
        db.add_entrada(chat_id, desc, valor)
    for desc, valor in context.user_data.get("despesas", []):
        db.add_despesa(chat_id, desc, valor, tipo="fixa")
    gastos_variaveis = context.user_data.get("gastos_variaveis", 0)
    if gastos_variaveis > 0:
        db.add_despesa(chat_id, "Gastos variáveis (estimativa)", gastos_variaveis, tipo="variavel")
    db.marcar_cadastro_completo(chat_id)

    total_entradas = db.total_entradas(chat_id)
    total_despesas = db.total_despesas(chat_id)
    saldo = total_entradas - total_despesas

    await update.effective_message.reply_text(
        f"Cadastro concluído, {nome}! 🎉\n\n"
        f"💵 Total de entradas: R$ {total_entradas:,.2f}\n"
        f"📉 Total de despesas (fixas + variáveis): R$ {total_despesas:,.2f}\n"
        f"💰 Saldo livre mensal: R$ {saldo:,.2f}\n\n"
        "Agora use /objetivo para definir uma meta e eu calculo o plano pra você chegar lá.\n"
        "Use /ajuda pra ver todos os comandos.",
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("Cadastro cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


cadastro_conv = ConversationHandler(
    entry_points=[CommandHandler("start", cadastro_start), CommandHandler("cadastro", cadastro_start)],
    states={
        NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
        RENDA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_renda)],
        OUTRA_ENTRADA_PERGUNTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, outra_entrada_pergunta)],
        OUTRA_ENTRADA_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, outra_entrada_desc)],
        OUTRA_ENTRADA_VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, outra_entrada_valor)],
        DESPESA_PERGUNTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, despesa_pergunta)],
        DESPESA_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, despesa_desc)],
        DESPESA_VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, despesa_valor)],
        GASTOS_VARIAVEIS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_gastos_variaveis)],
    },
    fallbacks=[CommandHandler("cancelar", cancelar)],
    conversation_timeout=900,
)
