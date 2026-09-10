"""
Baixa o modelo — no BUILD da imagem, nunca no start do contêiner.

POR QUE NO BUILD
----------------
Baixar no start faz cada reinício depender de duas coisas que não são nossas: a
rede do servidor e o Hugging Face estar de pé. Um restart às três da manhã
viraria um contêiner que sobe e não funciona, e o log diria "timeout" em vez de
"não consegui baixar 543 MB".

No build, se o download falhar, o BUILD falha — que é o lugar certo para
descobrir. E a imagem pronta sobe sem rede nenhuma.

POR QUE PRESO POR REVISÃO E HASH, E NÃO POR NOME
-------------------------------------------------
"bge-m3 quantizado" é um nome, não um arquivo. O mesmo nome hoje e daqui a seis
meses pode ser um arquivo diferente — o autor requantiza, corrige um bug,
troca a calibração. E embedding gerado por um modelo NÃO é comparável com o de
outro: os 74 trechos gravados continuariam no banco, a busca continuaria
rodando, e as distâncias passariam a ser entre vetores de dois espaços
diferentes. A busca pioraria sem um erro sequer — a mesma falha muda que já
apareceu duas vezes nesta fase.

Então são dois pinos, e cada um pega uma coisa:

- a **revisão** do repositório (commit) garante que a URL sempre aponta para o
  mesmo estado do repositório, mesmo que o autor publique depois;
- o **SHA-256** de cada arquivo garante que o que chegou é o que se esperava,
  mesmo que a revisão seja reescrita ou o download corrompa no meio.

Trocar de modelo é editar estas constantes de propósito — e aí a base inteira
precisa ser reembutida, porque os vetores velhos não valem mais.
"""

import hashlib
import sys
import time
import urllib.request
from pathlib import Path

REPO = "Xenova/bge-m3"

# Commit de `Xenova/bge-m3` conferido em 09/09/2026. Trocar isto é trocar de
# modelo: exige reembutir os 74 trechos.
REVISAO = "4de13258303883538bd53b696b452bf8099f0858"

ARQUIVOS = {
    "model_quantized.onnx": {
        "caminho": "onnx/model_quantized.onnx",
        "bytes": 569694530,
        "sha256": "0826f8c1ab9edf1801db86c61919d4d108e8bfc0b809ec823ad366882ff0b77d",
    },
    "tokenizer.json": {
        "caminho": "tokenizer.json",
        "bytes": 17082821,
        "sha256": "6710678b12670bc442b99edc952c4d996ae309a7020c1fa0096dd245c2faf790",
    },
}


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while bloco := f.read(1 << 20):
            h.update(bloco)
    return h.hexdigest()


def baixa(destino: Path, nome: str, info: dict, tentativas: int = 10) -> None:
    """
    Baixa com retomada. O arquivo tem 543 MB e a conexão cai — medido, caiu
    duas vezes no meio durante a avaliação do modelo.
    """
    arquivo = destino / nome
    url = f"https://huggingface.co/{REPO}/resolve/{REVISAO}/{info['caminho']}"

    for tentativa in range(1, tentativas + 1):
        ja = arquivo.stat().st_size if arquivo.exists() else 0
        if ja >= info["bytes"]:
            break
        req = urllib.request.Request(url, headers={"Range": f"bytes={ja}-"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r, open(arquivo, "ab") as f:
                while bloco := r.read(1 << 20):
                    f.write(bloco)
        except Exception as exc:  # noqa: BLE001
            print(f"  {nome}: tentativa {tentativa} caiu — {exc}", file=sys.stderr)
            time.sleep(3)

    tamanho = arquivo.stat().st_size if arquivo.exists() else 0
    if tamanho != info["bytes"]:
        raise SystemExit(
            f"ERRO: {nome} tem {tamanho} bytes, esperava {info['bytes']}. "
            "O build para aqui de propósito: imagem com modelo incompleto sobe e responde errado."
        )

    veio = sha256(arquivo)
    if veio != info["sha256"]:
        raise SystemExit(
            f"ERRO: {nome} tem SHA-256 {veio}, esperava {info['sha256']}.\n"
            "Ou o download corrompeu, ou o arquivo publicado MUDOU. No segundo caso, o modelo é "
            "outro e os embeddings já gravados deixam de ser comparáveis com os novos — a base "
            "inteira precisa ser reembutida. Não contorne trocando o hash sem reembutir."
        )
    print(f"  {nome}: {tamanho} bytes, SHA-256 confere")


def main() -> int:
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "/modelo")
    destino.mkdir(parents=True, exist_ok=True)
    print(f"Baixando {REPO} @ {REVISAO[:12]} para {destino}")
    for nome, info in ARQUIVOS.items():
        baixa(destino, nome, info)
    print("Modelo completo e conferido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
