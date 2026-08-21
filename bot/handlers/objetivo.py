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
from ..calculations import MODOS, formatar_plano, parse_data, parse_valor, simular_plano_mensal

NOME_OBJ, VALOR_OBJ, VALOR_ATUAL, DATA_OBJ, MODO_OBJ = range(100, 105)

MODO_KEYBOARD = ReplyKeyboardMarkup(
    [[MODOS[m]["label"] for m in MODOS]], one_time_keyboard=True, resize_keyboard=True
)


def calcular_planos_todos(chat_id: int):
    """Calcula o plano de todos os objetivos ativos, alocando o saldo livre
    em ordem de criação (o mais antigo tem prioridade sobre o saldo)."""
    objetivos = db.objetivos_ativos(chat_id)
    renda_total = db.total_entradas(chat_id)
    despesas = db.total_despesas(chat_id)
    parcelas = db.parcelas_por_mes(chat_id)

    resultados = []
    comprometido = 0.0
    for obj in objetivos:
        data_alvo = date.fromisoformat(obj["data_alvo"])
        plano = simular_plano_mensal(
            renda_total=renda_total,
            despesas_fixas=despesas,
            valor_atual=obj["valor_atual"],
            valor_alvo=obj["valor_alvo"],
            data_alvo=data_alvo,
            modo=obj["modo"],
            saldo_ja_comprometido=comprometido,
            parcelas_por_mes=parcelas,
        )
        resultados.append((obj, plano))
        comprometido += plano.aporte_sugerido
    return resultados


def modo_por_texto(texto: str) -> str | None:
    texto = texto.strip().lower()
    return next((m for m in MODOS if MODOS[m]["label"].lower() == texto or m == texto), None)


async def objetivo_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    if not db.usuario_existe(chat_id):
        await update.effective_message.reply_text("Antes de definir um objetivo, preciso do seu cadastro. Use /start.")
        return ConversationHandler.END

    context.user_data.clear()
    await update.effective_message.reply_text(
        "Vamos criar um objetivo. Como você quer chamar essa meta? (ex: Viagem, Reserva de emergência, Carro)",
        reply_markup=ReplyKeyboardRemove(),
    )
    return NOME_OBJ


async def receber_nome_obj(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["obj_nome"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("Qual é o valor total do objetivo? (ex: 10000)")
    return VALOR_OBJ


async def receber_valor_obj(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        valor = parse_valor(update.effective_message.text)
    except ValueError:
        await update.effective_message.reply_text("Não entendi o valor. Digite apenas números, ex: 10000")
        return VALOR_OBJ
    context.user_data["obj_valor_alvo"] = valor
    await update.effective_message.reply_text(
        "Você já tem algum valor guardado pra esse objetivo? Se não tiver, digite 0."
    )
    return VALOR_ATUAL


async def receber_valor_atual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        valor = parse_valor(update.effective_message.text)
    except ValueError:
        await update.effective_message.reply_text("Não entendi o valor. Digite apenas números, ex: 0")
        return VALOR_ATUAL
    context.user_data["obj_valor_atual"] = valor
    await update.effective_message.reply_text("Até qual data você quer atingir esse objetivo? (formato DD/MM/AAAA)")
    return DATA_OBJ


MAX_TENTATIVAS_DATA = 3


async def receber_data_obj(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        data_alvo = parse_data(update.effective_message.text)
    except ValueError as e:
        await update.effective_message.reply_text(str(e))
        return DATA_OBJ

    if data_alvo < date.today():
        tentativas = context.user_data.get("obj_data_tentativas", 0) + 1
        context.user_data["obj_data_tentativas"] = tentativas
        if tentativas < MAX_TENTATIVAS_DATA:
            await update.effective_message.reply_text(
                f"Essa data ({data_alvo.strftime('%d/%m/%Y')}) já passou — foi engano de digitação? "
                f"Manda de novo (tentativa {tentativas}/{MAX_TENTATIVAS_DATA}), formato DD/MM/AAAA."
            )
            return DATA_OBJ
        await update.effective_message.reply_text(
            "Ok, vou considerar essa data mesmo assim (já passada) — o plano vai calcular "
            "com base no próximo mês."
        )

    context.user_data["obj_data_alvo"] = data_alvo.isoformat()
    context.user_data.pop("obj_data_tentativas", None)
    await update.effective_message.reply_text(
        "Qual modo você quer usar?\n"
        "• Normal: ritmo confortável\n"
        "• Urgente: prioridade máxima, aperta o orçamento\n"
        "• Férias: ritmo constante até a data",
        reply_markup=MODO_KEYBOARD,
    )
    return MODO_OBJ


async def receber_modo_obj(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    modo = modo_por_texto(update.effective_message.text)
    if modo is None:
        await update.effective_message.reply_text("Escolha um dos modos disponíveis.", reply_markup=MODO_KEYBOARD)
        return MODO_OBJ

    chat_id = update.effective_chat.id
    nome = context.user_data["obj_nome"]
    valor_alvo = context.user_data["obj_valor_alvo"]
    valor_atual = context.user_data["obj_valor_atual"]
    data_alvo_iso = context.user_data["obj_data_alvo"]

    outros_ativos = len(db.objetivos_ativos(chat_id))
    db.criar_objetivo(chat_id, nome, valor_alvo, valor_atual, data_alvo_iso, modo)

    if outros_ativos > 0:
        await update.effective_message.reply_text(
            f"Objetivo criado! Você já tinha {outros_ativos} objetivo(s) ativo(s) — "
            "o saldo livre será dividido entre eles por ordem de criação.",
            reply_markup=ReplyKeyboardRemove(),
        )

    await enviar_todos_os_planos(update, context, chat_id)
    context.user_data.clear()
    return ConversationHandler.END


async def enviar_todos_os_planos(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    resultados = calcular_planos_todos(chat_id)
    if not resultados:
        await update.effective_message.reply_text("Você ainda não tem um objetivo ativo. Use /objetivo para criar um.")
        return

    for obj, plano in resultados:
        texto = formatar_plano(plano, obj["modo"], obj["nome"])
        await update.effective_message.reply_text(texto, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not db.usuario_existe(chat_id):
        await update.effective_message.reply_text("Você ainda não fez seu cadastro. Use /start.")
        return
    await enviar_todos_os_planos(update, context, chat_id)


async def cancelar_objetivo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("Criação de objetivo cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


objetivo_conv = ConversationHandler(
    entry_points=[CommandHandler("objetivo", objetivo_start)],
    states={
        NOME_OBJ: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome_obj)],
        VALOR_OBJ: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor_obj)],
        VALOR_ATUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor_atual)],
        DATA_OBJ: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_data_obj)],
        MODO_OBJ: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_modo_obj)],
    },
    fallbacks=[CommandHandler("cancelar", cancelar_objetivo)],
    conversation_timeout=900,
)

status_handler = CommandHandler("status", status)
