"""
Leitura de upload com limite — ponto único.

Os dois endpoints que recebem arquivo (anexo de chamado e foto de perfil)
faziam `await file.read()` e só então mediam `len(data)`. O limite era real,
mas chegava tarde: mandar 2 GB fazia o processo alocar 2 GB **antes** de
recusar, e não há middleware de tamanho de corpo na aplicação — o único
middleware montado é o CORS.

Aqui a leitura é por blocos e para no primeiro que cruza o limite. O pico de
memória passa a ser o próprio limite mais um bloco, e não o que quem chama
resolveu mandar.
"""

from fastapi import HTTPException, UploadFile, status

# 64 KB: grande o bastante para não virar um laço de milhares de iterações num
# anexo de 25 MB, pequeno o bastante para o excesso lido além do limite ser
# irrelevante.
_TAMANHO_DO_BLOCO = 64 * 1024


async def ler_ate_o_limite(file: UploadFile, max_bytes: int, rotulo: str) -> bytes:
    """
    Lê o arquivo em blocos, abortando assim que passar de ``max_bytes``.

    Args:
        file: O upload em andamento.
        max_bytes: Teto em bytes. Arquivo do tamanho exato do teto **passa**.
        rotulo: Como o limite aparece para o usuário na recusa (ex.: "25 MB").

    Returns:
        O conteúdo completo, quando cabe no limite.

    Raises:
        HTTPException: 413 assim que o acumulado ultrapassa ``max_bytes``.
            413 e não 422: o pedido está bem formado, o que não cabe é o
            tamanho — e o front já traduz 413 sozinho.
    """
    blocos: list[bytes] = []
    total = 0

    while True:
        bloco = await file.read(_TAMANHO_DO_BLOCO)
        if not bloco:
            break

        total += len(bloco)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"O arquivo '{file.filename}' passa do limite de {rotulo}. "
                    "Envie um arquivo menor."
                ),
            )

        blocos.append(bloco)

    return b"".join(blocos)
