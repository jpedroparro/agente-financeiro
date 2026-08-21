from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

TEXTO_AJUDA = (
    "🤖 *Comandos disponíveis*\n\n"
    "/start — cadastro inicial (nome, renda, despesas)\n"
    "/cadastro — refazer o cadastro do zero\n"
    "/objetivo — criar um novo objetivo financeiro\n"
    "/status — ver o plano de todos os objetivos ativos\n"
    "/aporte — registrar quanto você guardou este mês\n"
    "/modo — trocar o modo (Normal/Urgente/Férias) de um objetivo\n"
    "/editar — remover uma entrada ou despesa cadastrada\n"
    "/fatura — importar um PDF de fatura de cartão e reconhecer parcelas\n"
    "/parcelas — ver o cronograma de parcelas futuras do cartão\n"
    "/perfil — ver entradas, despesas e objetivo(s) ativo(s)\n"
    "/cancelar — cancelar uma operação em andamento\n"
    "/ajuda — ver esta mensagem"
)


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(TEXTO_AJUDA, parse_mode="Markdown")


ajuda_handler = CommandHandler("ajuda", ajuda)
