"""
Gate de auditoria de dependências: falha quando aparece vulnerabilidade NOVA.

O CI não tinha nada disso, e por isso ninguém sabia que havia 24 avisos no
backend — descobertos à mão na auditoria de 01/09/2026. Uma delas era alcançável
de fora, num endpoint público.

O que este gate faz e o que ele NÃO faz:

  • falha para vulnerabilidade fora do baseline  <- o ponto
  • falha para entrada de baseline sem justificativa
  • falha para entrada obsoleta, cuja vulnerabilidade não aparece mais
  • NÃO falha para o que está no baseline com motivo escrito

A terceira é chata de propósito. Consertar uma dependência passa a quebrar o CI
até alguém limpar o arquivo — mas a mensagem diz exatamente qual linha apagar, é
conserto de dez segundos, e sem isso o baseline vira lista que só cresce. Lista
que só cresce ninguém lê, e gate que ninguém lê não é gate.

── A CHAVE É O ADVISORY, NÃO O PACOTE ────────────────────────────────────────

A primeira versão indexava o front por PACOTE. Era mais curto — uma linha cobria
os dez avisos do `react-router` — e tinha um buraco que anulava o gate: advisory
NOVO num pacote já listado passava calado. É exatamente a classe de coisa que
este arquivo existe para pegar.

Pior que o buraco: a justificativa acabava escrita para UM advisory e herdada
por todos os outros do mesmo pacote. O `react-router` tinha `motivo` falando de
RSC/turbo-stream, e debaixo dele passavam dois open redirects de
`<Link>`/`useNavigate` que o argumento de RSC não explica.

Agora a chave é `pacote + advisory` — GHSA quando existe, id do npm quando não,
e um digest de título+severidade+faixa como último recurso. Uma justificativa
por vulnerabilidade real.

Pacotes sinalizados só por herança (o `via` do npm aponta para outro pacote, sem
advisory próprio) não viram chave, de propósito: o aviso deles é o do pacote de
baixo, que já tem entrada. Saem impressos como contexto, para ninguém achar que
deixaram de ser vigiados.

Testes: backend/tests/test_gate_dependencias.py

Uso:

    python .github/scripts/verifica_dependencias.py                 # os dois
    python .github/scripts/verifica_dependencias.py --lado backend
    python .github/scripts/verifica_dependencias.py --lado frontend

Sem dependência nova: usa `tomllib`, que é stdlib desde o Python 3.11.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
BASELINE = RAIZ / ".github" / "dependencias-conhecidas.toml"

_OBRIGATORIOS = ("motivo", "remover_quando", "classe")
_CLASSES = {
    "nao_aplicavel",
    "mitigado_na_aplicacao",
    "mitigado_por_configuracao",
    "aceito_com_prazo",
}


def _carrega_baseline() -> dict:
    if not BASELINE.is_file():
        sys.exit(f"ERRO: baseline não encontrado em {BASELINE}")
    with BASELINE.open("rb") as f:
        return tomllib.load(f)


def chave_de_entrada(entrada: dict, lado: str) -> str:
    """A chave de uma linha do baseline, no mesmo formato que a auditoria gera.

    Backend é o `id` puro: o pip-audit já devolve identificador global
    (PYSEC-…, GHSA-…). O front precisa do pacote junto, porque o mesmo GHSA pode
    atingir dois pacotes da árvore e cada um merece a sua própria justificativa.
    """
    if lado == "backend":
        return str(entrada.get("id", "")).strip()
    pacote = str(entrada.get("pacote", "")).strip()
    advisory = str(entrada.get("advisory", "")).strip()
    return f"{pacote} {advisory}" if pacote and advisory else ""


# ── Backend ───────────────────────────────────────────────────


def chaves_do_pip_audit(dados: dict) -> dict[str, dict]:
    """Mapeia id -> detalhe a partir do JSON do pip-audit. Puro, testável."""
    achados: dict[str, dict] = {}
    for dep in dados.get("dependencies", []):
        for v in dep.get("vulns", []):
            detalhe = dict(v)
            detalhe.setdefault("name", dep.get("name", ""))
            achados[v["id"]] = detalhe
    return achados


def _audita_backend() -> tuple[dict[str, dict], list[str]]:
    req = RAIZ / "backend" / "requirements.txt"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "-r",
            str(req),
            "--format",
            "json",
            "--progress-spinner",
            "off",
        ],
        capture_output=True,
        text=True,
    )
    # pip-audit sai com código != 0 quando ACHA vulnerabilidade. Isso é o caso
    # normal aqui, não erro: quem decide o veredito é este script.
    if not proc.stdout.strip():
        sys.exit(f"ERRO: pip-audit não devolveu JSON.\n{proc.stderr[:800]}")
    return chaves_do_pip_audit(json.loads(proc.stdout)), []


# ── Frontend ──────────────────────────────────────────────────


def id_do_advisory(via: dict) -> str:
    """Identificador estável de um advisory do npm.

    Ordem de preferência: GHSA (padrão, cruza com CVE e é legível), id numérico
    do npm, e só então um digest de título+severidade+faixa. O último recurso
    existe para que advisory sem id NUNCA seja descartado em silêncio — se ele
    ficasse de fora do conjunto de achados, o gate deixaria de vigiá-lo sem
    dizer nada, que é o defeito que esta versão veio corrigir.
    """
    url = str(via.get("url") or "").rstrip("/")
    ultimo = url.rsplit("/", 1)[-1] if url else ""
    if ultimo.upper().startswith(("GHSA-", "CVE-")):
        return ultimo
    fonte = via.get("source")
    if fonte:
        return f"npm-{fonte}"
    material = "|".join(str(via.get(c, "")) for c in ("title", "severity", "range"))
    return "sem-id-" + hashlib.sha1(material.encode("utf-8")).hexdigest()[:12]


def chaves_do_npm_audit(dados: dict) -> tuple[dict[str, dict], list[str]]:
    """Mapeia `pacote GHSA` -> detalhe a partir do JSON do npm audit. Puro.

    Devolve também os pacotes que o npm sinaliza SEM advisory próprio — o `via`
    deles é só o nome de outro pacote.
    """
    vulnerabilidades = dados.get("vulnerabilities", {})
    achados: dict[str, dict] = {}
    com_advisory_proprio: set[str] = set()

    for pacote, info in vulnerabilidades.items():
        for via in info.get("via", []):
            if not isinstance(via, dict):
                continue
            nome = str(via.get("name") or via.get("dependency") or pacote)
            com_advisory_proprio.add(nome)
            detalhe = dict(via)
            detalhe["name"] = nome
            achados[f"{nome} {id_do_advisory(via)}"] = detalhe

    heranca = sorted(p for p in vulnerabilidades if p not in com_advisory_proprio)
    return achados, heranca


def _audita_frontend() -> tuple[dict[str, dict], list[str]]:
    front = RAIZ / "frontend"
    proc = subprocess.run(
        ["npm", "audit", "--json"],
        capture_output=True,
        text=True,
        cwd=front,
        shell=sys.platform == "win32",
    )
    if not proc.stdout.strip():
        sys.exit(f"ERRO: npm audit não devolveu JSON.\n{proc.stderr[:800]}")
    return chaves_do_npm_audit(json.loads(proc.stdout))


# ── Comparação ────────────────────────────────────────────────


def valida_entradas(entradas: list[dict], lado: str) -> list[str]:
    """Baseline mal preenchido é falha, e não aviso.

    Uma entrada sem `motivo` é indistinguível de um ignore feito às pressas para
    o CI passar — que é exatamente o que este gate existe para impedir.
    """
    problemas = []
    for i, e in enumerate(entradas, 1):
        chave = chave_de_entrada(e, lado)
        nome = chave or f"entrada #{i}"
        if not chave:
            campos = "id" if lado == "backend" else "pacote + advisory"
            problemas.append(f"[{lado}] entrada #{i}: sem chave ({campos})")
        for campo in _OBRIGATORIOS:
            if not str(e.get(campo, "")).strip():
                problemas.append(f"[{lado}] {nome}: campo '{campo}' vazio ou ausente")
        classe = e.get("classe", "")
        if classe and classe not in _CLASSES:
            problemas.append(
                f"[{lado}] {nome}: classe '{classe}' desconhecida. Use uma de: "
                + ", ".join(sorted(_CLASSES))
            )
    return problemas


def compara(
    achados: dict[str, dict], entradas: list[dict], lado: str
) -> tuple[list[str], list[str]]:
    conhecidos = {c for c in (chave_de_entrada(e, lado) for e in entradas) if c}
    novos = sorted(set(achados) - conhecidos)
    obsoletos = sorted(conhecidos - set(achados))
    return novos, obsoletos


def _descreve(detalhe: dict) -> str:
    """O que a pessoa precisa ver para decidir, sem ter de rodar a auditoria de novo."""
    cabecalho = [str(detalhe[c]) for c in ("severity", "range") if detalhe.get(c)]
    linhas = []
    if cabecalho:
        linhas.append("           " + " · ".join(cabecalho))
    titulo = detalhe.get("title") or detalhe.get("description") or ""
    if titulo:
        linhas.append("           " + str(titulo).strip().splitlines()[0][:100])
    if detalhe.get("url"):
        linhas.append(f"           {detalhe['url']}")
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    # O console do Windows usa cp1252 e estoura em acento e em caractere de
    # caixa. O CI é Ubuntu/UTF-8 e passaria — o defeito só apareceria na máquina
    # de quem desenvolve, que é justamente onde este script mais precisa rodar.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lado", choices=["backend", "frontend"], default=None)
    args = parser.parse_args(argv)

    baseline = _carrega_baseline()
    lados = [args.lado] if args.lado else ["backend", "frontend"]

    falhas: list[str] = []
    for lado in lados:
        entradas = baseline.get(lado, [])
        falhas.extend(valida_entradas(entradas, lado))

        achados, heranca = (
            _audita_backend() if lado == "backend" else _audita_frontend()
        )
        novos, obsoletos = compara(achados, entradas, lado)

        print(f"\n-- {lado} --------------------------------------")
        print(f"  advisories hoje : {len(achados)}")
        print(f"  no baseline     : {len(entradas)}")
        if heranca:
            print("  so por heranca  : " + ", ".join(heranca))
            print(
                "                    (sem advisory proprio; o aviso e o do pacote de baixo)"
            )

        for n in novos:
            detalhe = _descreve(achados[n])
            falhas.append(
                f"[{lado}] VULNERABILIDADE NOVA: {n}\n"
                + (detalhe + "\n" if detalhe else "")
                + "           Não está no baseline. A pergunta NÃO é como fazer o CI passar,\n"
                "           e sim: esse código é alcançável no HelpHS?\n"
                "           Alcançável -> conserte. Inalcançável -> acrescente em\n"
                "           .github/dependencias-conhecidas.toml com o COMANDO que provou."
            )
        for o in obsoletos:
            falhas.append(
                f"[{lado}] ENTRADA OBSOLETA: {o}\n"
                "           A vulnerabilidade não aparece mais — provavelmente foi corrigida.\n"
                "           Apague esta entrada de .github/dependencias-conhecidas.toml."
            )

        if not novos and not obsoletos:
            print("  OK: nenhuma vulnerabilidade nova fora do baseline")

    if falhas:
        print("\n" + "=" * 70)
        print("GATE DE DEPENDÊNCIAS: FALHOU")
        print("=" * 70)
        for f in falhas:
            print(f"\n  {f}")
        print()
        return 1

    print("\nGate de dependências: executado com baseline conhecido;")
    print("nenhuma vulnerabilidade nova fora do baseline.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
