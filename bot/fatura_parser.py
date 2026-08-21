import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
import pytesseract
from PIL import Image

from .calculations import parse_valor

_TESSDATA_DIR = Path(__file__).resolve().parent.parent / "tessdata"
_TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if Path(_TESSERACT_CMD).exists():
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD
_OCR_CONFIG = f"--tessdata-dir {_TESSDATA_DIR}"

# Reconhece linhas terminadas em "DESCRICAO ... N/M VALOR", ex:
#   "AMAZON BR MARKETPLACE  03/05  250,00"
#   "MAGAZINE LUIZA 3/10 R$ 189,90"
_PADRAO_PARCELA = re.compile(
    r"^(?P<desc>.+?)\s+(?P<atual>\d{1,2})\s*/\s*(?P<total>\d{1,2})\s+"
    r"(?:R\$\s*)?(?P<valor>\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*$"
)


@dataclass
class CompraParcelada:
    descricao: str
    numero_parcela: int
    total_parcelas: int
    valor: float
    linha_original: str


def extrair_texto(caminho_pdf: str) -> str:
    partes = []
    with pdfplumber.open(caminho_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            partes.append(texto)
    return "\n".join(partes)


def extrair_texto_imagem(caminho_imagem: str) -> str:
    imagem = Image.open(caminho_imagem)
    return pytesseract.image_to_string(imagem, lang="por", config=_OCR_CONFIG)


def parsear_compras_parceladas(texto: str) -> list[CompraParcelada]:
    resultado = []
    for linha_bruta in texto.splitlines():
        linha = linha_bruta.strip()
        if not linha:
            continue
        match = _PADRAO_PARCELA.match(linha)
        if not match:
            continue

        desc = match.group("desc").strip(" -*")
        if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", desc)) < 3:
            continue  # descrição sem letras suficientes, provavelmente falso positivo

        atual = int(match.group("atual"))
        total = int(match.group("total"))
        if not (1 <= atual <= total <= 48):
            continue

        try:
            valor = parse_valor(match.group("valor"))
        except ValueError:
            continue

        resultado.append(
            CompraParcelada(
                descricao=desc,
                numero_parcela=atual,
                total_parcelas=total,
                valor=valor,
                linha_original=linha,
            )
        )
    return resultado
