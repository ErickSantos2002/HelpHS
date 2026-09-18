"""
Testes do gate de auditoria de dependências (`.github/scripts/verifica_dependencias.py`).

Moram aqui, e não ao lado do script, porque aqui eles ROD AM: o job de backend do
CI já executa `pytest`, e um teste que ninguém executa protege tanto quanto um
gate com `continue-on-error`.

O teste central é `test_advisory_novo_em_pacote_ja_listado_derruba_o_gate`. Ele
existe por causa de um defeito real: a primeira versão do gate indexava o front
por PACOTE, então um advisory NOVO num pacote já listado passava calado — a
única coisa que o gate precisa pegar. Nenhum teste apontava para isso porque
todos verificavam o caminho feliz.

Nada aqui toca a rede: `npm audit` e `pip-audit` entram como JSON de mentira, com
a forma do de verdade.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "verifica_dependencias.py"
_spec = importlib.util.spec_from_file_location("verifica_dependencias", _SCRIPT)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


# ── Fábricas ──────────────────────────────────────────────────


def via(
    pacote: str,
    ghsa: str,
    severidade: str = "high",
    faixa: str = "<1.0.0",
    titulo: str = "titulo do advisory",
) -> dict[str, Any]:
    """Um advisory na forma que o `npm audit --json` devolve."""
    return {
        "source": 1234567,
        "name": pacote,
        "dependency": pacote,
        "title": titulo,
        "url": f"https://github.com/advisories/{ghsa}",
        "severity": severidade,
        "range": faixa,
    }


def audit(*advisories: dict[str, Any], heranca: tuple[tuple[str, str], ...] = ()) -> dict[str, Any]:
    vulnerabilidades: dict[str, Any] = {}
    for a in advisories:
        vulnerabilidades.setdefault(a["name"], {"via": []})["via"].append(a)
    for pacote, aponta_para in heranca:
        vulnerabilidades[pacote] = {"via": [aponta_para]}
    return {"vulnerabilities": vulnerabilidades}


def entrada(pacote: str, advisory: str, **campos: str) -> dict[str, str]:
    base = {
        "pacote": pacote,
        "advisory": advisory,
        "classe": "nao_aplicavel",
        "motivo": "`npm ls --omit=dev` -> ausente da arvore de producao",
        "remover_quando": "o pacote entrar na arvore de producao",
    }
    base.update(campos)
    return base


def roda(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    baseline: list[dict[str, Any]],
    dados_do_npm: dict[str, Any],
) -> tuple[int, str]:
    achados, heranca = gate.chaves_do_npm_audit(dados_do_npm)
    monkeypatch.setattr(gate, "_carrega_baseline", lambda: {"frontend": baseline})
    monkeypatch.setattr(gate, "_audita_frontend", lambda: (achados, heranca))
    codigo = gate.main(["--lado", "frontend"])
    return codigo, capsys.readouterr().out


# ── O caso que estava cego ────────────────────────────────────


def test_advisory_novo_em_pacote_ja_listado_derruba_o_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """O buraco da versão por pacote: `axios` já no baseline, advisory novo nele.

    Indexando por pacote, `axios` estava listado e o gate passava — mesmo com um
    aviso crítico recém-publicado. É o defeito que motivou a troca de chave.
    """
    codigo, saida = roda(
        monkeypatch,
        capsys,
        baseline=[entrada("axios", "GHSA-ja-conhecido")],
        dados_do_npm=audit(
            via("axios", "GHSA-ja-conhecido"),
            via(
                "axios",
                "GHSA-recem-publicado",
                severidade="critical",
                titulo="RCE no axios",
            ),
        ),
    )

    assert codigo == 1
    assert "VULNERABILIDADE NOVA: axios GHSA-recem-publicado" in saida
    # A mensagem precisa bastar para escrever a entrada sem rodar a auditoria de
    # novo: severidade, título e link.
    assert "critical" in saida
    assert "RCE no axios" in saida
    assert "https://github.com/advisories/GHSA-recem-publicado" in saida


def test_o_mesmo_cenario_passa_quando_o_advisory_novo_e_declarado(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Contraprova do teste acima: o que derruba é o advisory novo, e nada mais.

    Sem este par, um erro qualquer em `main` faria o teste anterior passar pelo
    motivo errado.
    """
    codigo, saida = roda(
        monkeypatch,
        capsys,
        baseline=[
            entrada("axios", "GHSA-ja-conhecido"),
            entrada("axios", "GHSA-recem-publicado"),
        ],
        dados_do_npm=audit(
            via("axios", "GHSA-ja-conhecido"),
            via("axios", "GHSA-recem-publicado", severidade="critical"),
        ),
    )

    assert codigo == 0
    assert "nenhuma vulnerabilidade nova fora do baseline" in saida


def test_entrada_so_com_pacote_e_recusada(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A forma antiga do baseline não pode voltar a ser aceita em silêncio."""
    antiga = {
        "pacote": "axios",
        "classe": "nao_aplicavel",
        "motivo": "transitiva de build",
        "remover_quando": "nunca",
    }

    codigo, saida = roda(
        monkeypatch,
        capsys,
        baseline=[antiga],
        dados_do_npm=audit(via("axios", "GHSA-x")),
    )

    assert codigo == 1
    assert "sem chave (pacote + advisory)" in saida


# ── Demais modos de falha ─────────────────────────────────────


def test_entrada_obsoleta_derruba_o_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    codigo, saida = roda(
        monkeypatch,
        capsys,
        baseline=[entrada("axios", "GHSA-ja-corrigido")],
        dados_do_npm=audit(),
    )

    assert codigo == 1
    assert "ENTRADA OBSOLETA: axios GHSA-ja-corrigido" in saida


@pytest.mark.parametrize("campo", ["motivo", "remover_quando", "classe"])
def test_entrada_sem_justificativa_derruba_o_gate(
    campo: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    codigo, saida = roda(
        monkeypatch,
        capsys,
        baseline=[entrada("axios", "GHSA-x", **{campo: ""})],
        dados_do_npm=audit(via("axios", "GHSA-x")),
    )

    assert codigo == 1
    assert f"campo '{campo}' vazio ou ausente" in saida


def test_classe_desconhecida_derruba_o_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    codigo, saida = roda(
        monkeypatch,
        capsys,
        baseline=[entrada("axios", "GHSA-x", classe="depois_a_gente_ve")],
        dados_do_npm=audit(via("axios", "GHSA-x")),
    )

    assert codigo == 1
    assert "classe 'depois_a_gente_ve' desconhecida" in saida


def test_baseline_em_dia_passa(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    codigo, saida = roda(
        monkeypatch,
        capsys,
        baseline=[entrada("axios", "GHSA-x"), entrada("vite", "GHSA-y")],
        dados_do_npm=audit(via("axios", "GHSA-x"), via("vite", "GHSA-y")),
    )

    assert codigo == 0
    assert "advisories hoje : 2" in saida


# ── Leitura do JSON do npm ────────────────────────────────────


def test_a_chave_junta_pacote_e_advisory() -> None:
    achados, _ = gate.chaves_do_npm_audit(audit(via("axios", "GHSA-abc")))

    assert set(achados) == {"axios GHSA-abc"}


def test_pacote_sinalizado_so_por_heranca_nao_vira_chave() -> None:
    """`react-router-dom` é sinalizado só porque depende de `react-router`.

    O aviso é o do pacote de baixo, que tem entrada própria. Contar os dois faria
    o baseline pedir justificativa duplicada para a mesma vulnerabilidade.
    """
    achados, heranca = gate.chaves_do_npm_audit(
        audit(
            via("react-router", "GHSA-abc"),
            heranca=(("react-router-dom", "react-router"),),
        )
    )

    assert set(achados) == {"react-router GHSA-abc"}
    assert heranca == ["react-router-dom"]


def test_o_mesmo_advisory_em_dois_pacotes_gera_duas_chaves() -> None:
    """Uma justificativa por pacote afetado: o alcance pode ser diferente em cada."""
    achados, _ = gate.chaves_do_npm_audit(
        audit(via("axios", "GHSA-abc"), via("form-data", "GHSA-abc"))
    )

    assert set(achados) == {"axios GHSA-abc", "form-data GHSA-abc"}


def test_advisory_sem_ghsa_cai_para_o_id_do_npm() -> None:
    sem_url = via("axios", "ignorado")
    sem_url["url"] = ""

    assert gate.id_do_advisory(sem_url) == "npm-1234567"


def test_advisory_sem_id_nenhum_ainda_recebe_chave_estavel() -> None:
    """Sem chave, ele sumiria do conjunto de achados — e deixaria de ser vigiado."""
    anonimo = {"name": "axios", "title": "t", "severity": "high", "range": "<1"}

    primeira = gate.id_do_advisory(anonimo)
    segunda = gate.id_do_advisory(dict(anonimo))

    assert primeira.startswith("sem-id-")
    assert primeira == segunda
    assert gate.id_do_advisory({**anonimo, "severity": "critical"}) != primeira


def test_backend_continua_indexado_por_id() -> None:
    dados = {
        "dependencies": [{"name": "jinja2", "vulns": [{"id": "GHSA-9999", "fix_versions": []}]}]
    }

    achados = gate.chaves_do_pip_audit(dados)

    assert set(achados) == {"GHSA-9999"}
    assert gate.chave_de_entrada({"id": "GHSA-9999"}, "backend") == "GHSA-9999"


# ── O arquivo de verdade ──────────────────────────────────────


def test_o_baseline_do_repositorio_esta_bem_formado() -> None:
    """Sem rede: só valida o que está escrito no arquivo que vai para o CI."""
    baseline = gate._carrega_baseline()

    problemas = gate.valida_entradas(baseline["backend"], "backend")
    problemas += gate.valida_entradas(baseline["frontend"], "frontend")

    assert problemas == []


def test_o_baseline_do_repositorio_nao_tem_chave_repetida() -> None:
    baseline = gate._carrega_baseline()

    for lado in ("backend", "frontend"):
        chaves = [gate.chave_de_entrada(e, lado) for e in baseline[lado]]
        repetidas = {c for c in chaves if chaves.count(c) > 1}
        assert repetidas == set(), f"{lado}: chave repetida {repetidas}"
