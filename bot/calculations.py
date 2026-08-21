from dataclasses import dataclass
from datetime import date, datetime

MODOS = {
    "normal": {
        "label": "Normal",
        "percentual_saldo": 0.30,
        "descricao": "Ritmo confortável: guarda uma fatia do saldo livre sem apertar o orçamento.",
    },
    "urgente": {
        "label": "Urgente",
        "percentual_saldo": 0.70,
        "descricao": "Prioridade máxima no objetivo: reserva a maior parte possível do saldo livre.",
    },
    "ferias": {
        "label": "Férias",
        "percentual_saldo": 0.45,
        "descricao": "Ritmo constante mirando exatamente na data alvo, sem sobressaltos.",
    },
}


@dataclass
class PlanoFinanceiro:
    meses_restantes: int
    saldo_livre: float
    faltante: float
    aporte_necessario: float
    aporte_sugerido: float
    factivel: bool
    excedente_ou_deficit: float
    atrasado: bool = False
    mes_mais_apertado: str | None = None
    saldo_mes_mais_apertado: float | None = None


def meses_ate(data_alvo: date, hoje: date | None = None) -> tuple[int, bool]:
    """Retorna (meses_restantes, atrasado). meses_restantes nunca é menor que 1
    pra evitar divisão por zero; atrasado indica que a data alvo já passou."""
    hoje = hoje or date.today()
    if data_alvo < hoje:
        return 1, True
    meses = (data_alvo.year - hoje.year) * 12 + (data_alvo.month - hoje.month)
    if data_alvo.day < hoje.day:
        meses -= 1
    return max(meses, 1), False


def mes_str(d: date) -> str:
    return d.strftime("%Y-%m")


def somar_meses(ano_mes: str, n: int) -> str:
    ano, mes = (int(x) for x in ano_mes.split("-"))
    total = (ano * 12 + (mes - 1)) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def parse_valor(texto: str) -> float:
    """Converte texto digitado pelo usuário em float, aceitando tanto o formato
    brasileiro (1.500,50) quanto o formato com ponto decimal simples (1500.50)."""
    texto = texto.strip().replace("R$", "").replace(" ", "")
    if not texto:
        raise ValueError("Valor vazio.")

    tem_virgula = "," in texto
    tem_ponto = "." in texto

    if tem_virgula and tem_ponto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif tem_virgula:
        partes = texto.split(",")
        texto = texto.replace(",", "") if len(partes[-1]) == 3 else texto.replace(",", ".")
    elif tem_ponto:
        partes = texto.split(".")
        if len(partes) > 1 and len(partes[-1]) == 3:
            texto = texto.replace(".", "")

    valor = float(texto)
    if valor < 0:
        raise ValueError("Valor não pode ser negativo.")
    return valor


def parse_data(texto: str) -> date:
    texto = texto.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    raise ValueError("Data inválida. Use o formato DD/MM/AAAA.")


def calcular_plano(
    renda_total: float,
    despesas_fixas: float,
    valor_atual: float,
    valor_alvo: float,
    data_alvo: date,
    modo: str = "normal",
    saldo_ja_comprometido: float = 0.0,
) -> PlanoFinanceiro:
    """saldo_ja_comprometido: parte do saldo livre já reservada por outros objetivos
    ativos, descontada antes de calcular o plano deste objetivo (permite ter
    vários objetivos simultâneos dividindo o mesmo saldo livre)."""
    modo = modo if modo in MODOS else "normal"
    meses, atrasado = meses_ate(data_alvo)
    saldo_livre_total = max(renda_total - despesas_fixas, 0.0)
    saldo_livre = max(saldo_livre_total - saldo_ja_comprometido, 0.0)
    faltante = max(valor_alvo - valor_atual, 0.0)

    aporte_necessario = faltante / meses if meses > 0 else faltante

    percentual = MODOS[modo]["percentual_saldo"]
    aporte_sugerido = min(saldo_livre * percentual, saldo_livre)

    if modo == "ferias":
        # No modo férias, tenta convergir exatamente na data, respeitando o teto do saldo livre
        aporte_sugerido = min(aporte_necessario, saldo_livre)

    factivel = aporte_necessario <= saldo_livre
    excedente_ou_deficit = saldo_livre - aporte_necessario

    return PlanoFinanceiro(
        meses_restantes=meses,
        saldo_livre=round(saldo_livre, 2),
        faltante=round(faltante, 2),
        aporte_necessario=round(aporte_necessario, 2),
        aporte_sugerido=round(aporte_sugerido, 2),
        factivel=factivel,
        excedente_ou_deficit=round(excedente_ou_deficit, 2),
        atrasado=atrasado,
    )


def simular_plano_mensal(
    renda_total: float,
    despesas_fixas: float,
    valor_atual: float,
    valor_alvo: float,
    data_alvo: date,
    modo: str = "normal",
    saldo_ja_comprometido: float = 0.0,
    parcelas_por_mes: dict | None = None,
) -> PlanoFinanceiro:
    """Como calcular_plano, mas simula mês a mês considerando parcelas de cartão
    que vencem em meses específicos (parcelas_por_mes: {'YYYY-MM': valor}), em vez
    de assumir uma despesa fixa igual todo mês. Isso deixa o plano ciente de meses
    em que o saldo livre vai apertar por causa de parcelas vencendo."""
    modo = modo if modo in MODOS else "normal"
    meses, atrasado = meses_ate(data_alvo)
    parcelas_por_mes = parcelas_por_mes or {}
    percentual = MODOS[modo]["percentual_saldo"]

    saldo_acumulado = valor_atual
    hoje = date.today()
    mes_mais_apertado = None
    saldo_mes_mais_apertado = None
    saldo_livre_mes1 = None

    for i in range(meses):
        ref = somar_meses(mes_str(hoje), i)
        parcelas_mes = parcelas_por_mes.get(ref, 0.0)
        saldo_livre_mes = max(renda_total - despesas_fixas - parcelas_mes - saldo_ja_comprometido, 0.0)
        if i == 0:
            saldo_livre_mes1 = saldo_livre_mes
        if saldo_mes_mais_apertado is None or saldo_livre_mes < saldo_mes_mais_apertado:
            saldo_mes_mais_apertado = saldo_livre_mes
            mes_mais_apertado = ref

        if modo == "ferias":
            faltante_atual = max(valor_alvo - saldo_acumulado, 0.0)
            meses_restantes_loop = meses - i
            aporte_mes = (
                min(faltante_atual / meses_restantes_loop, saldo_livre_mes)
                if meses_restantes_loop > 0
                else min(faltante_atual, saldo_livre_mes)
            )
        else:
            aporte_mes = min(saldo_livre_mes * percentual, saldo_livre_mes)

        saldo_acumulado += aporte_mes

    faltante = max(valor_alvo - valor_atual, 0.0)
    aporte_necessario = faltante / meses if meses > 0 else faltante
    aporte_sugerido_mes1 = min((saldo_livre_mes1 or 0.0) * percentual, saldo_livre_mes1 or 0.0)
    if modo == "ferias":
        aporte_sugerido_mes1 = min(aporte_necessario, saldo_livre_mes1 or 0.0)

    factivel = saldo_acumulado >= valor_alvo

    # Só reporta o mês mais apertado se houver parcelas de fato afetando a projeção
    if not parcelas_por_mes or all(v == 0 for v in parcelas_por_mes.values()):
        mes_mais_apertado = None
        saldo_mes_mais_apertado = None

    return PlanoFinanceiro(
        meses_restantes=meses,
        saldo_livre=round(saldo_livre_mes1 or 0.0, 2),
        faltante=round(faltante, 2),
        aporte_necessario=round(aporte_necessario, 2),
        aporte_sugerido=round(aporte_sugerido_mes1, 2),
        factivel=factivel,
        excedente_ou_deficit=round((saldo_livre_mes1 or 0.0) - aporte_necessario, 2),
        atrasado=atrasado,
        mes_mais_apertado=mes_mais_apertado,
        saldo_mes_mais_apertado=round(saldo_mes_mais_apertado, 2) if saldo_mes_mais_apertado is not None else None,
    )


def formatar_plano(plano: PlanoFinanceiro, modo: str, nome_objetivo: str) -> str:
    modo_info = MODOS.get(modo, MODOS["normal"])
    linhas = [
        f"📊 *Plano para \"{nome_objetivo}\"* (modo {modo_info['label']})",
        f"_{modo_info['descricao']}_",
        "",
    ]
    if plano.atrasado:
        linhas.append("⚠️ A data alvo já passou — os números abaixo consideram o próximo mês.")
    linhas += [
        f"🗓 Meses restantes: {plano.meses_restantes}",
        f"💰 Saldo livre disponível p/ este objetivo: R$ {plano.saldo_livre:,.2f}",
        f"🎯 Falta juntar: R$ {plano.faltante:,.2f}",
        f"📌 Aporte mensal necessário: R$ {plano.aporte_necessario:,.2f}",
        f"✅ Aporte sugerido no modo {modo_info['label']}: R$ {plano.aporte_sugerido:,.2f}",
        "",
    ]
    if plano.factivel:
        linhas.append(
            f"🟢 Objetivo factível! Sobra R$ {plano.excedente_ou_deficit:,.2f}/mês além do necessário."
        )
    else:
        linhas.append(
            f"🔴 Com o saldo livre disponível, falta R$ {abs(plano.excedente_ou_deficit):,.2f}/mês. "
            "Considere reduzir despesas, aumentar renda ou estender o prazo."
        )
    if plano.mes_mais_apertado:
        linhas.append(
            f"📎 Mês mais apertado pelas parcelas do cartão: {plano.mes_mais_apertado} "
            f"(saldo livre de R$ {plano.saldo_mes_mais_apertado:,.2f} naquele mês)."
        )
    return "\n".join(linhas)
