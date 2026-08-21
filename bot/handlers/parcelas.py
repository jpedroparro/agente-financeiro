from collections import defaultdict

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from .. import db
from ..calculations import mes_str
from datetime import date


async def parcelas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not db.usuario_existe(chat_id):
        await update.effective_message.reply_text("Você ainda não fez seu cadastro. Use /start.")
        return

    mes_atual = mes_str(date.today())
    itens = db.listar_parcelas_futuras(chat_id, mes_atual)
    if not itens:
        await update.effective_message.reply_text(
            "Nenhuma parcela cadastrada. Use /fatura pra importar uma fatura do cartão."
        )
        return

    por_mes = defaultdict(list)
    for i in itens:
        por_mes[i["mes_vencimento"]].append(i)

    linhas = ["🗂 *Parcelas futuras*", ""]
    for mes in sorted(por_mes):
        total_mes = sum(i["valor"] for i in por_mes[mes])
        linhas.append(f"*{mes}* — total R$ {total_mes:,.2f}")
        for i in por_mes[mes]:
            linhas.append(f"  • {i['descricao']} ({i['numero_parcela']}/{i['total_parcelas']}): R$ {i['valor']:,.2f}")
        linhas.append("")

    await update.effective_message.reply_text("\n".join(linhas), parse_mode="Markdown")


parcelas_handler = CommandHandler("parcelas", parcelas)
