import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "financeiro.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    chat_id INTEGER PRIMARY KEY,
    nome TEXT,
    cadastro_completo INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS entradas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    descricao TEXT NOT NULL,
    valor REAL NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES usuarios(chat_id)
);

CREATE TABLE IF NOT EXISTS despesas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    descricao TEXT NOT NULL,
    valor REAL NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'fixa',
    FOREIGN KEY (chat_id) REFERENCES usuarios(chat_id)
);

CREATE TABLE IF NOT EXISTS objetivos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    valor_alvo REAL NOT NULL,
    valor_atual REAL NOT NULL DEFAULT 0,
    data_alvo TEXT NOT NULL,
    modo TEXT NOT NULL DEFAULT 'normal',
    ativo INTEGER NOT NULL DEFAULT 1,
    concluido INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (chat_id) REFERENCES usuarios(chat_id)
);

CREATE TABLE IF NOT EXISTS aportes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    objetivo_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    valor REAL NOT NULL,
    criado_em TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (objetivo_id) REFERENCES objetivos(id)
);

CREATE TABLE IF NOT EXISTS cartoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    criado_em TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (chat_id) REFERENCES usuarios(chat_id)
);

CREATE TABLE IF NOT EXISTS faturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    cartao_id INTEGER NOT NULL,
    mes_referencia TEXT NOT NULL,
    criado_em TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (cartao_id) REFERENCES cartoes(id)
);

CREATE TABLE IF NOT EXISTS parcelas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    cartao_id INTEGER NOT NULL,
    descricao TEXT NOT NULL,
    numero_parcela INTEGER NOT NULL,
    total_parcelas INTEGER NOT NULL,
    valor REAL NOT NULL,
    mes_vencimento TEXT NOT NULL,
    criado_em TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (cartao_id) REFERENCES cartoes(id),
    UNIQUE (cartao_id, descricao, total_parcelas, numero_parcela)
);
"""

_MIGRATIONS = [
    ("despesas", "tipo", "TEXT NOT NULL DEFAULT 'fixa'"),
    ("objetivos", "concluido", "INTEGER NOT NULL DEFAULT 0"),
]


def _migrar(conn):
    for tabela, coluna, definicao in _MIGRATIONS:
        colunas = {row["name"] for row in conn.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in colunas:
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrar(conn)


def upsert_usuario(chat_id: int, nome: str):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO usuarios (chat_id, nome) VALUES (?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET nome=excluded.nome""",
            (chat_id, nome),
        )


def marcar_cadastro_completo(chat_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE usuarios SET cadastro_completo = 1 WHERE chat_id = ?", (chat_id,)
        )


def usuario_existe(chat_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM usuarios WHERE chat_id = ? AND cadastro_completo = 1",
            (chat_id,),
        ).fetchone()
        return row is not None


def limpar_entradas_despesas(chat_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM entradas WHERE chat_id = ?", (chat_id,))
        conn.execute("DELETE FROM despesas WHERE chat_id = ?", (chat_id,))


def add_entrada(chat_id: int, descricao: str, valor: float):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO entradas (chat_id, descricao, valor) VALUES (?, ?, ?)",
            (chat_id, descricao, valor),
        )


def add_despesa(chat_id: int, descricao: str, valor: float, tipo: str = "fixa"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO despesas (chat_id, descricao, valor, tipo) VALUES (?, ?, ?, ?)",
            (chat_id, descricao, valor, tipo),
        )


def listar_entradas(chat_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, descricao, valor FROM entradas WHERE chat_id = ? ORDER BY id", (chat_id,)
        ).fetchall()


def listar_despesas(chat_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, descricao, valor, tipo FROM despesas WHERE chat_id = ? ORDER BY id", (chat_id,)
        ).fetchall()


def remover_entrada(chat_id: int, entrada_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM entradas WHERE id = ? AND chat_id = ?", (entrada_id, chat_id)
        )
        return cur.rowcount > 0


def remover_despesa(chat_id: int, despesa_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM despesas WHERE id = ? AND chat_id = ?", (despesa_id, chat_id)
        )
        return cur.rowcount > 0


def total_entradas(chat_id: int) -> float:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(valor), 0) AS total FROM entradas WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        return row["total"]


def total_despesas(chat_id: int, tipo: str | None = None) -> float:
    with get_conn() as conn:
        if tipo:
            row = conn.execute(
                "SELECT COALESCE(SUM(valor), 0) AS total FROM despesas WHERE chat_id = ? AND tipo = ?",
                (chat_id, tipo),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(valor), 0) AS total FROM despesas WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return row["total"]


def criar_objetivo(
    chat_id: int,
    nome: str,
    valor_alvo: float,
    valor_atual: float,
    data_alvo: str,
    modo: str,
):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO objetivos (chat_id, nome, valor_alvo, valor_atual, data_alvo, modo)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chat_id, nome, valor_alvo, valor_atual, data_alvo, modo),
        )


def objetivos_ativos(chat_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM objetivos WHERE chat_id = ? AND ativo = 1 AND concluido = 0 ORDER BY id",
            (chat_id,),
        ).fetchall()


def objetivo_por_id(objetivo_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM objetivos WHERE id = ?", (objetivo_id,)
        ).fetchone()


def atualizar_modo(objetivo_id: int, modo: str):
    with get_conn() as conn:
        conn.execute("UPDATE objetivos SET modo = ? WHERE id = ?", (modo, objetivo_id))


def registrar_aporte(objetivo_id: int, chat_id: int, valor: float):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO aportes (objetivo_id, chat_id, valor) VALUES (?, ?, ?)",
            (objetivo_id, chat_id, valor),
        )
        conn.execute(
            "UPDATE objetivos SET valor_atual = valor_atual + ? WHERE id = ?",
            (valor, objetivo_id),
        )
        row = conn.execute(
            "SELECT valor_atual, valor_alvo FROM objetivos WHERE id = ?", (objetivo_id,)
        ).fetchone()
        if row and row["valor_atual"] >= row["valor_alvo"]:
            conn.execute(
                "UPDATE objetivos SET concluido = 1 WHERE id = ?", (objetivo_id,)
            )
        return row


def get_or_criar_cartao(chat_id: int, nome: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM cartoes WHERE chat_id = ? AND nome = ?", (chat_id, nome)
        ).fetchone()
        if row:
            return row["id"]
        cur = conn.execute(
            "INSERT INTO cartoes (chat_id, nome) VALUES (?, ?)", (chat_id, nome)
        )
        return cur.lastrowid


def listar_cartoes(chat_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, nome FROM cartoes WHERE chat_id = ? ORDER BY id", (chat_id,)
        ).fetchall()


def registrar_fatura(chat_id: int, cartao_id: int, mes_referencia: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO faturas (chat_id, cartao_id, mes_referencia) VALUES (?, ?, ?)",
            (chat_id, cartao_id, mes_referencia),
        )
        return cur.lastrowid


def salvar_parcelas(chat_id: int, cartao_id: int, parcelas: list[dict]):
    """parcelas: lista de dicts com descricao, numero_parcela, total_parcelas, valor, mes_vencimento.
    Usa upsert por (cartao_id, descricao, total_parcelas, numero_parcela) pra evitar
    duplicar a mesma compra ao reimportar uma fatura que já contém parcelas antigas."""
    with get_conn() as conn:
        for p in parcelas:
            conn.execute(
                """INSERT INTO parcelas
                       (chat_id, cartao_id, descricao, numero_parcela, total_parcelas, valor, mes_vencimento)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(cartao_id, descricao, total_parcelas, numero_parcela)
                   DO UPDATE SET valor = excluded.valor, mes_vencimento = excluded.mes_vencimento""",
                (
                    chat_id,
                    cartao_id,
                    p["descricao"],
                    p["numero_parcela"],
                    p["total_parcelas"],
                    p["valor"],
                    p["mes_vencimento"],
                ),
            )


def parcelas_por_mes(chat_id: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT mes_vencimento, COALESCE(SUM(valor), 0) AS total
               FROM parcelas WHERE chat_id = ? GROUP BY mes_vencimento""",
            (chat_id,),
        ).fetchall()
        return {row["mes_vencimento"]: row["total"] for row in rows}


def listar_parcelas_futuras(chat_id: int, a_partir_de: str):
    with get_conn() as conn:
        return conn.execute(
            """SELECT descricao, numero_parcela, total_parcelas, valor, mes_vencimento
               FROM parcelas WHERE chat_id = ? AND mes_vencimento >= ?
               ORDER BY mes_vencimento, descricao""",
            (chat_id, a_partir_de),
        ).fetchall()


def usuarios_com_objetivos_ativos():
    with get_conn() as conn:
        return conn.execute(
            """SELECT DISTINCT chat_id FROM objetivos
               WHERE ativo = 1 AND concluido = 0"""
        ).fetchall()
