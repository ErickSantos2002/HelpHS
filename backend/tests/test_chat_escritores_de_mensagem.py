"""
Quem grava em `chat_messages` — e se cada um passa pela numeração (F1-B-04c).

A garantia do `after_seq` vale só para mensagem numerada no fim da transação
que a grava. Um escritor novo que esqueça `numera_mensagens_do_chat` não
quebra nada à vista: a mensagem aparece na tela por `created_at`, e some
apenas para quem sincroniza por número. Este teste é o que torna isso
visível — ele lê o código, não o executa.

Se ele falhar porque você criou um escritor novo: faça a transação dona
chamar `numera_mensagens_do_chat(db)` imediatamente antes do commit (e
depois da Helô, ver a ordem dos bloqueios em `app/services/chat_sequencia.py`),
prove isso com um teste em PostgreSQL e acrescente o escritor aqui.
"""

import ast
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
_ONDE_SE_GRAVA = ("app", "scripts")

# Onde um `ChatMessage(...)` é construído — arquivo e função que o constrói.
_ESCRITORES = {
    ("app/routers/chat.py", "create_message"),
    ("app/routers/chat.py", "websocket_chat"),
    ("app/services/helo.py", "abre_triagem"),
    ("app/services/helo.py", "responde_triagem"),
}

# Quem chama os escritores da Helô: elas não comitam, e a numeração é do
# dono da transação em que rodam.
_QUEM_CHAMA_A_HELO = {
    "abre_triagem": {("app/routers/tickets.py", "create_ticket")},
    "_fala_da_helo_sem_derrubar": {
        ("app/routers/chat.py", "create_message"),
        ("app/routers/chat.py", "websocket_chat"),
    },
    "responde_triagem": {("app/routers/chat.py", "_fala_da_helo_sem_derrubar")},
}

# Os donos das transações que gravam mensagem, e a chamada da Helô dentro de
# cada um — a numeração precisa vir DEPOIS dela.
_DONOS = {
    ("app/routers/chat.py", "create_message"): "_fala_da_helo_sem_derrubar",
    ("app/routers/chat.py", "websocket_chat"): "_fala_da_helo_sem_derrubar",
    ("app/routers/tickets.py", "create_ticket"): "abre_triagem",
}
_COMMITS = {"commit", "commit_e_notificar"}


def _arquivos():
    for pasta in _ONDE_SE_GRAVA:
        for arquivo in sorted((_RAIZ / pasta).rglob("*.py")):
            yield arquivo.relative_to(_RAIZ).as_posix(), ast.parse(
                arquivo.read_text(encoding="utf-8")
            )


def _funcoes(arvore):
    """(função, nó) para cada chamada, com a função MAIS INTERNA que a contém."""
    pilha: list[str] = []

    def _visita(no):
        e_funcao = isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef)
        if e_funcao:
            pilha.append(no.name)
        if isinstance(no, ast.Call):
            yield (pilha[-1] if pilha else "<módulo>"), no
        for filho in ast.iter_child_nodes(no):
            yield from _visita(filho)
        if e_funcao:
            pilha.pop()

    yield from _visita(arvore)


def _nome(chamada: ast.Call) -> str | None:
    f = chamada.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def _funcao(arquivo: str, nome: str) -> ast.AST:
    arvore = ast.parse((_RAIZ / arquivo).read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef) and no.name == nome:
            return no
    raise AssertionError(f"{nome} sumiu de {arquivo}")


def _linhas_das_chamadas(no: ast.AST, nome: str) -> list[int]:
    return sorted(c.lineno for c in ast.walk(no) if isinstance(c, ast.Call) and _nome(c) == nome)


def test_os_escritores_de_mensagem_sao_os_conhecidos():
    achados = {
        (arquivo, funcao)
        for arquivo, arvore in _arquivos()
        for funcao, chamada in _funcoes(arvore)
        if _nome(chamada) == "ChatMessage"
    }
    assert achados == _ESCRITORES


def test_ninguem_grava_mensagem_por_fora_do_orm():
    """`insert(ChatMessage)` e SQL cru não passam pelo evento que anota a
    mensagem na sessão — sairiam sem número, em silêncio."""
    proibidos = []
    for arquivo, arvore in _arquivos():
        for no in ast.walk(arvore):
            if (
                isinstance(no, ast.Call)
                and _nome(no) == "insert"
                and any(isinstance(a, ast.Name) and a.id == "ChatMessage" for a in no.args)
            ):
                proibidos.append((arquivo, no.lineno, "insert(ChatMessage)"))
            if isinstance(no, ast.Constant) and isinstance(no.value, str):
                sql = " ".join(no.value.lower().split())
                if "insert into chat_messages" in sql:
                    proibidos.append((arquivo, no.lineno, "INSERT cru"))
    assert proibidos == []


def test_os_escritores_da_helo_so_rodam_dentro_dos_donos_conhecidos():
    for alvo, esperado in _QUEM_CHAMA_A_HELO.items():
        achados = {
            (arquivo, funcao)
            for arquivo, arvore in _arquivos()
            for funcao, chamada in _funcoes(arvore)
            if _nome(chamada) == alvo
        }
        assert achados == esperado, alvo


def test_cada_dono_numera_depois_da_helo_e_antes_de_todo_commit():
    for (arquivo, funcao), helo in _DONOS.items():
        corpo = _funcao(arquivo, funcao)
        numeracoes = _linhas_das_chamadas(corpo, "numera_mensagens_do_chat")
        commits = sorted(
            c.lineno for c in ast.walk(corpo) if isinstance(c, ast.Call) and _nome(c) in _COMMITS
        )
        da_helo = _linhas_das_chamadas(corpo, helo)
        assert numeracoes, f"{funcao} não numera"
        assert commits, f"{funcao} não comita?"
        assert da_helo, f"{funcao} não chama {helo}?"
        # Cada commit tem uma numeração antes dele, e depois da Helô.
        for commit in commits:
            antes = [n for n in numeracoes if n < commit]
            assert antes, f"{funcao}: commit na linha {commit} sem numeração antes"
            assert max(antes) > max(
                h for h in da_helo if h < commit
            ), f"{funcao}: a numeração precisa vir DEPOIS da Helô — o contador é o último bloqueio"
