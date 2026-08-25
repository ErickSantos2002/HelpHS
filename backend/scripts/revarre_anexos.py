"""
Revarredura: passa o ClamAV nos anexos que entraram sem exame.

**Avulso, rodado à mão, NUNCA em migration** — regra do projeto: dado histórico
se corrige em script, regra nova é prospectiva. As migrations rodam sozinhas no
boot do container no EasyPanel; este script não pode supor nada disso e não é
chamado por ninguém.

Por que existem anexos sem exame
--------------------------------
O upload chama o ClamAV, mas quando ele está fora do ar a varredura volta
``unavailable`` e o arquivo é **aceito assim mesmo** (ver ``attachments.py``) —
bloquear derrubaria o anexo inteiro por causa de um serviço auxiliar. Esses
arquivos ficam gravados com ``virus_scanned=False``. Enquanto o ClamAV não
existiu no ambiente, foi assim com **todos**.

Depois de subir o ClamAV, este script varre o que ficou para trás.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'
    export UPLOAD_DIR=/app/uploads          # onde os anexos estão gravados
    export CLAMAV_HOST=clamav               # e CLAMAV_PORT, se não for 3310

    python -m scripts.revarre_anexos              # dry-run: só relata
    python -m scripts.revarre_anexos --aplicar    # grava o resultado

Sem ``--aplicar`` nada é escrito. O relatório sai igual nos dois modos, então
dá para conferir antes e comparar depois.

O que o script NÃO faz
----------------------
Não apaga nada, nem arquivo infectado. Um script de limpeza que descarta o que
não entende é pior que o problema que veio consertar — e um anexo é prova de um
chamado. Infectado é **relatado em destaque** e deixado como está, com
``virus_scanned=True`` e ``virus_clean=False``, para que a decisão seja de quem
lê o relatório. Arquivo que sumiu do disco também é só relatado.
"""

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# O console do Windows abre em cp1252 e estoura em qualquer acento — e este
# script roda na máquina de quem administra, não no container. Sem isto o
# relatório morre com UnicodeEncodeError antes de mostrar a primeira linha.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import antivirus  # noqa: E402


@dataclass(frozen=True)
class Resultado:
    """O que a varredura concluiu sobre um anexo."""

    anexo_id: str
    nome: str
    situacao: str  # "limpo" | "infectado" | "sem_arquivo" | "sem_resposta"
    detalhe: str

    @property
    def grava(self) -> bool:
        """Só limpo e infectado viraram exame; o resto não mudou de estado."""
        return self.situacao in ("limpo", "infectado")

    @property
    def limpo(self) -> bool:
        return self.situacao == "limpo"


async def varre_um(anexo_id: str, nome: str, caminho: Path, host: str, port: int) -> Resultado:
    """
    Varre um arquivo e traduz a resposta do ClamAV em situação.

    Separada da parte que grava porque é aqui que mora a decisão: é esta função
    que diz o que vai ser marcado como examinado.
    """
    if not caminho.is_file():
        return Resultado(anexo_id, nome, "sem_arquivo", f"não está em {caminho}")

    try:
        dados = caminho.read_bytes()
    except OSError as exc:
        return Resultado(anexo_id, nome, "sem_arquivo", f"não deu para ler: {exc}")

    ok, msg = await antivirus.scan_bytes(dados, host=host, port=port)

    if msg == "clean":
        return Resultado(anexo_id, nome, "limpo", "clean")
    if msg.startswith("Virus:"):
        return Resultado(anexo_id, nome, "infectado", msg)
    # "unavailable" ou "error: ..." — o ClamAV não deu veredito, então o anexo
    # continua sem exame. Marcar como examinado aqui seria inventar resultado.
    return Resultado(anexo_id, nome, "sem_resposta", msg)


def _relata(resultados: list[Resultado]) -> None:
    por_situacao: dict[str, list[Resultado]] = {}
    for r in resultados:
        por_situacao.setdefault(r.situacao, []).append(r)

    print("\n── Resumo " + "─" * 50)
    for situacao in ("limpo", "infectado", "sem_arquivo", "sem_resposta"):
        print(f"  {situacao:14} {len(por_situacao.get(situacao, [])):>5}")

    infectados = por_situacao.get("infectado", [])
    if infectados:
        print("\n" + "!" * 60)
        print(f"!! {len(infectados)} ANEXO(S) INFECTADO(S) — nada foi apagado.")
        print("!! Decida à mão o que fazer com cada um:")
        for r in infectados:
            print(f"!!   {r.anexo_id}  {r.nome}  {r.detalhe}")
        print("!" * 60)

    for rotulo, titulo in (
        ("sem_arquivo", "Sem o arquivo no disco (registro órfão)"),
        ("sem_resposta", "ClamAV não deu veredito — continuam sem exame"),
    ):
        itens = por_situacao.get(rotulo, [])
        if itens:
            print(f"\n  {titulo}:")
            for r in itens:
                print(f"    {r.anexo_id}  {r.nome}  ({r.detalhe})")


async def _main(aplicar: bool) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Defina DATABASE_URL antes de rodar.")

    upload_dir = Path(os.environ.get("UPLOAD_DIR", "/app/uploads")).resolve()
    host = os.environ.get("CLAMAV_HOST", "clamav")
    port = int(os.environ.get("CLAMAV_PORT", "3310"))

    modo = "APLICANDO" if aplicar else "DRY-RUN (nada será gravado)"
    print(f"Revarredura de anexos — {modo}")
    print(f"  arquivos em: {upload_dir}")
    print(f"  ClamAV em:   {host}:{port}")

    if not await antivirus.ping(host, port):
        raise SystemExit(
            f"\nClamAV não respondeu em {host}:{port}. Sem ele o script não tem o que "
            "fazer — subir o serviço primeiro é o passo que este script pressupõe."
        )
    print("  ClamAV respondeu: PONG")

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            linhas = (
                await conn.execute(
                    text(
                        "SELECT id, original_name, s3_key FROM attachments "
                        "WHERE virus_scanned = false ORDER BY created_at"
                    )
                )
            ).all()

        print(f"\n{len(linhas)} anexo(s) sem exame.")
        if not linhas:
            print("Nada a fazer.")
            return

        resultados = [
            await varre_um(str(r.id), r.original_name, upload_dir / r.s3_key, host, port)
            for r in linhas
        ]
        _relata(resultados)

        gravaveis = [r for r in resultados if r.grava]
        if aplicar and gravaveis:
            async with engine.connect() as conn:
                for r in gravaveis:
                    await conn.execute(
                        text(
                            "UPDATE attachments SET virus_scanned = true, virus_clean = :limpo "
                            "WHERE id = :id"
                        ),
                        {"limpo": r.limpo, "id": r.anexo_id},
                    )
                await conn.commit()
            print(f"\n  OK: {len(gravaveis)} anexo(s) marcado(s) como examinado(s).")
        elif not aplicar and gravaveis:
            print(
                f"\n{len(gravaveis)} anexo(s) seriam marcados como examinados. "
                "Rode de novo com --aplicar para gravar."
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revarredura de anexos sem exame de antivírus.")
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="grava o resultado da varredura; sem esta flag o script só relata",
    )
    asyncio.run(_main(parser.parse_args().aplicar))
