from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from .. import db


async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not db.usuario_existe(chat_id):
        await update.effective_message.reply_text("Você ainda não fez seu cadastro. Use /start.")
        return

    entradas = db.listar_entradas(chat_id)
    despesas = db.listar_despesas(chat_id)
    total_entradas = db.total_entradas(chat_id)
    total_despesas = db.total_despesas(chat_id)

    linhas = ["💵 *Entradas*"]
    linhas += [f"• {e['descricao']} (#{e['id']}): R$ {e['valor']:,.2f}" for e in entradas] or ["Nenhuma"]
    linhas.append("")
    linhas.append("📉 *Despesas*")
    linhas += [
        f"• {d['descricao']} (#{d['id']}) [{d['tipo']}]: R$ {d['valor']:,.2f}" for d in despesas
    ] or ["Nenhuma"]
    linhas.append("")
    linhas.append(f"💰 Saldo livre mensal: R$ {total_entradas - total_despesas:,.2f}")

    objetivos = db.objetivos_ativos(chat_id)
    linhas.append("")
    if objetivos:
        linhas.append("🎯 *Objetivos ativos*")
        for o in objetivos:
            linhas.append(
                f"• {o['nome']}: R$ {o['valor_atual']:,.2f} / R$ {o['valor_alvo']:,.2f} "
                f"até {o['data_alvo']} (modo {o['modo']})"
            )
    else:
        linhas.append("Nenhum objetivo ativo. Use /objetivo para criar um.")

    await update.effective_message.reply_text("\n".join(linhas), parse_mode="Markdown")


perfil_handler = CommandHandler("perfil", perfil)
