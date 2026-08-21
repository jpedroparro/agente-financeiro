import logging
import tempfile
from pathlib import Path

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CommandHandler,
    filters,
)

from .. import db
from ..calculations import parse_data, somar_meses, mes_str
from ..fatura_parser import extrair_texto, extrair_texto_imagem, parsear_compras_parceladas

logger = logging.getLogger(__name__)

CARTAO, MES_REFERENCIA, AGUARDANDO_ARQUIVO, CONFIRMAR = range(500, 504)

SIM_NAO = ReplyKeyboardMarkup([["Sim", "Não"]], one_time_keyboard=True, resize_keyboard=True)


async def fatura_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    if not db.usuario_existe(chat_id):
        await update.effective_message.reply_text("Você ainda não fez seu cadastro. Use /start.")
        return ConversationHandler.END

    context.user_data.clear()
    cartoes = db.listar_cartoes(chat_id)
    if cartoes:
        teclado = ReplyKeyboardMarkup(
            [[c["nome"]] for c in cartoes], one_time_keyboard=True, resize_keyboard=True
        )
        await update.effective_message.reply_text(
            "De qual cartão é essa fatura? (digite o nome de um existente ou um nome novo)",
            reply_markup=teclado,
        )
    else:
        await update.effective_message.reply_text(
            "De qual cartão é essa fatura? (dê um nome, ex: Nubank, Inter)",
            reply_markup=ReplyKeyboardRemove(),
        )
    return CARTAO


async def receber_cartao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nome = update.effective_message.text.strip()
    context.user_data["fatura_cartao_nome"] = nome
    await update.effective_message.reply_text(
        "Qual o mês de referência dessa fatura? (formato MM/AAAA, ex: 09/2026)",
        reply_markup=ReplyKeyboardRemove(),
    )
    return MES_REFERENCIA


async def receber_mes_referencia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.effective_message.text.strip()
    try:
        data = parse_data(f"01/{texto}")
    except ValueError:
        await update.effective_message.reply_text("Não entendi. Use o formato MM/AAAA, ex: 09/2026")
        return MES_REFERENCIA
    context.user_data["fatura_mes_referencia"] = mes_str(data)
    context.user_data["fatura_compras_acumuladas"] = []
    await update.effective_message.reply_text(
        "Beleza! Agora me envie o PDF da fatura, ou fotos/prints das telas (pode mandar "
        "várias fotos, uma por vez). Quando terminar de enviar as fotos, digite 'pronto'.\n\n"
        "⚠️ O reconhecimento das parcelas é melhor-esforço — o layout varia entre bancos e a "
        "qualidade da foto importa bastante pro OCR. Vou te mostrar o que encontrei antes de salvar."
    )
    return AGUARDANDO_ARQUIVO


async def receber_conteudo_invalido(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Não entendi. Envie o PDF da fatura, uma foto da tela, digite 'pronto' se já mandou "
        "as fotos, ou /cancelar."
    )
    return AGUARDANDO_ARQUIVO


def _resumo_compras(compras, titulo: str) -> str:
    linhas = [titulo, ""]
    for c in compras[:20]:
        linhas.append(f"• {c.descricao} — parcela {c.numero_parcela}/{c.total_parcelas} — R$ {c.valor:,.2f}")
    if len(compras) > 20:
        linhas.append(f"... e mais {len(compras) - 20}")
    return "\n".join(linhas)


async def receber_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    documento = update.effective_message.document
    if not documento or not documento.file_name.lower().endswith(".pdf"):
        await update.effective_message.reply_text("Preciso de um arquivo PDF. Envie o arquivo da fatura.")
        return AGUARDANDO_ARQUIVO

    arquivo = await context.bot.get_file(documento.file_id)
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "fatura.pdf"
        await arquivo.download_to_drive(custom_path=str(caminho))
        try:
            texto = extrair_texto(str(caminho))
        except Exception:
            logger.exception("Falha ao extrair texto do PDF")
            await update.effective_message.reply_text(
                "Não consegui ler esse PDF (pode estar protegido por senha ou ser uma imagem escaneada)."
            )
            return AGUARDANDO_ARQUIVO

    compras = parsear_compras_parceladas(texto)
    if not compras:
        await update.effective_message.reply_text(
            "Não reconheci nenhuma compra parcelada nesse PDF. Pode mandar fotos das telas "
            "também, ou digite 'pronto' pra encerrar."
        )
        return AGUARDANDO_ARQUIVO

    context.user_data["fatura_compras_acumuladas"].extend(compras)
    return await _perguntar_confirmacao(update, context)


async def receber_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    fotos = update.effective_message.photo
    if not fotos:
        return await receber_conteudo_invalido(update, context)

    maior_foto = fotos[-1]
    arquivo = await context.bot.get_file(maior_foto.file_id)
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "fatura.jpg"
        await arquivo.download_to_drive(custom_path=str(caminho))
        try:
            texto = extrair_texto_imagem(str(caminho))
        except Exception:
            logger.exception("Falha ao rodar OCR na imagem")
            await update.effective_message.reply_text(
                "Não consegui processar essa imagem. Tente outra foto (mais nítida, sem cortar "
                "as bordas) ou mande o PDF da fatura."
            )
            return AGUARDANDO_ARQUIVO

    compras = parsear_compras_parceladas(texto)
    if not compras:
        await update.effective_message.reply_text(
            "Não reconheci nenhuma parcela nessa foto (o OCR pode ter tido dificuldade). "
            "Pode mandar outra foto, o PDF, ou digitar 'pronto' pra encerrar."
        )
        return AGUARDANDO_ARQUIVO

    context.user_data["fatura_compras_acumuladas"].extend(compras)
    total_acumulado = len(context.user_data["fatura_compras_acumuladas"])
    await update.effective_message.reply_text(
        _resumo_compras(compras, f"✅ Reconheci {len(compras)} compra(s) nessa foto:")
        + f"\n\nTotal acumulado até agora: {total_acumulado}. Manda mais fotos ou digite 'pronto'."
    )
    return AGUARDANDO_ARQUIVO


async def marcar_pronto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message.text.strip().lower() != "pronto":
        return await receber_conteudo_invalido(update, context)

    compras = context.user_data.get("fatura_compras_acumuladas", [])
    if not compras:
        await update.effective_message.reply_text(
            "Ainda não recebi nenhuma foto ou PDF reconhecido. Envie ao menos um antes de "
            "digitar 'pronto', ou /cancelar."
        )
        return AGUARDANDO_ARQUIVO

    return await _perguntar_confirmacao(update, context)


async def _perguntar_confirmacao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    compras = context.user_data["fatura_compras_acumuladas"]
    texto = _resumo_compras(compras, "📋 *No total, reconheci estas compras parceladas:*")
    texto += "\n\nPosso salvar essas parcelas (incluindo as futuras que ainda vão vencer)?"
    await update.effective_message.reply_text(texto, parse_mode="Markdown", reply_markup=SIM_NAO)
    return CONFIRMAR


async def confirmar_salvar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    resposta = update.effective_message.text.strip().lower()
    if not resposta.startswith("s"):
        context.user_data.clear()
        await update.effective_message.reply_text("Ok, não salvei nada.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    chat_id = update.effective_chat.id
    nome_cartao = context.user_data["fatura_cartao_nome"]
    mes_referencia = context.user_data["fatura_mes_referencia"]
    compras = context.user_data["fatura_compras_acumuladas"]

    cartao_id = db.get_or_criar_cartao(chat_id, nome_cartao)
    db.registrar_fatura(chat_id, cartao_id, mes_referencia)

    parcelas_para_salvar = []
    for c in compras:
        meses_restantes = c.total_parcelas - c.numero_parcela
        for offset in range(meses_restantes + 1):
            numero = c.numero_parcela + offset
            parcelas_para_salvar.append(
                {
                    "descricao": c.descricao,
                    "numero_parcela": numero,
                    "total_parcelas": c.total_parcelas,
                    "valor": c.valor,
                    "mes_vencimento": somar_meses(mes_referencia, offset),
                }
            )

    db.salvar_parcelas(chat_id, cartao_id, parcelas_para_salvar)

    await update.effective_message.reply_text(
        f"Salvei {len(compras)} compra(s) parcelada(s) do cartão {nome_cartao}, "
        f"projetando {len(parcelas_para_salvar)} parcela(s) no total. ✅\n\n"
        "Use /parcelas pra ver o cronograma ou /status pra ver o plano atualizado.",
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancelar_fatura(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("Importação de fatura cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


fatura_conv = ConversationHandler(
    entry_points=[CommandHandler("fatura", fatura_start)],
    states={
        CARTAO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_cartao)],
        MES_REFERENCIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_mes_referencia)],
        AGUARDANDO_ARQUIVO: [
            MessageHandler(filters.Document.PDF, receber_pdf),
            MessageHandler(filters.PHOTO, receber_foto),
            MessageHandler(filters.Regex(r"(?i)^pronto$"), marcar_pronto),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receber_conteudo_invalido),
        ],
        CONFIRMAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_salvar)],
    },
    fallbacks=[CommandHandler("cancelar", cancelar_fatura)],
    conversation_timeout=900,
)
