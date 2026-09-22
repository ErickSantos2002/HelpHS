"""
Transporte da API4COM: sabe fazer `POST /calls` e mais nada.

**Nesta fase ninguém chama este módulo.** Nenhum router, nenhum lifespan,
nenhum laço de fundo o importa — de propósito. O código existe, sabe montar a
requisição e sabe classificar a falha, mas em produção a Fase 2A continua
incapaz de iniciar ligação por ausência de consumidor. Quem for ligar o
primeiro consumidor precisa ler o resto deste texto antes.

Por que um módulo só de transporte
----------------------------------
Iniciar ligação é a **primeira escrita externa** do HelpHS. Todas as outras
chamadas que saem daqui são leitura (ViaCEP, BrasilAPI) ou idempotentes na
prática (DeepSeek, embedding). Escrita externa traz um problema que nenhuma
delas tem: quando a resposta não volta, **não dá para saber se o outro lado
agiu**. E aqui "agir" significa tocar o telefone de uma pessoa.

Por isso o módulo não decide nada de domínio. Ele não normaliza telefone, não
escolhe ramal, não sabe o que é chamado nem cliente. `caller`, `called` e
`extension` chegam prontos e saem **byte a byte como chegaram** — a regra
brasileira de número mora em `app/utils/telefone.py` e a camada de domínio da
Fase 2C é quem a aplica. Transporte que "conserta" o número cria uma segunda
fonte de verdade que deriva da primeira em silêncio.

O que NUNCA pode virar retry
----------------------------
Medido no `httpcore` 1.0.9 instalado: o único laço de retentativa do httpx está
em `_connect()` e captura estritamente `(ConnectError, ConnectTimeout)` — ele
cobre o aperto de mão TCP/TLS e **nenhum byte de requisição é escrito ali**. O
default de `retries` já é 0, mas aqui ele vai **explícito** no transporte, e
`follow_redirects` vai explicitamente desligado: um 307 ou 308 preserva método
e corpo (`httpx/_client.py:494-515`), e seguir redirect automaticamente seria o
único caminho pelo qual esta casa criaria duas ligações com um clique.

`httpcore` é dependência transitiva e **não está pinada** — só `httpcore==1.*`
pelo metadado do httpx. Se um rebuild mudar esse comportamento, quem avisa é o
teste que prende `await_count == 1` em `tests/test_api4com.py`, não este
comentário.

As quatro categorias de falha, e por que são quatro
---------------------------------------------------
A pergunta que cada uma responde é sempre a mesma: **a ligação saiu?**

- `Api4ComDesligadaError` — a chave está desligada. Erro de uso, não do provedor;
  levantado antes de existir cliente HTTP. Não devolve `None` em silêncio como
  o `llm.py` faz: lá o silêncio é o estado normal de produção, aqui chamar o
  transporte com a integração desligada é defeito de quem chamou.
- `Api4ComIndisponivelError` — não houve comunicação HTTP útil: a conexão falhou
  antes de a requisição ser escrita.
- `Api4ComRecusadaError` — **só 4xx**. O fornecedor respondeu rejeitando a
  requisição, e carregamos apenas o status.
- `Api4ComResultadoIndeterminadoError` — tudo o mais. **Pode estar tocando.**

A tabela, porque a linha entre a terceira e a quarta é a que custa caro:

===============================  ==================================
 situação                         a ligação saiu?
===============================  ==================================
 flag desligada                   não houve tentativa
 ConnectError / ConnectTimeout    não houve comunicação HTTP útil
 HTTP 4xx                         rejeição HTTP confirmada
 HTTP 5xx                         INDETERMINADO
 HTTP 3xx                         INDETERMINADO
 transporte após conexão          INDETERMINADO
 2xx com corpo ilegível           INDETERMINADO
===============================  ==================================

⚠️ **5xx não é prova de que a ligação não saiu.** O fornecedor pode ter recebido
o POST, disparado a chamada e só então quebrado por dentro: o 500 descreve o
estado do servidor dele, não o do telefone de quem ia receber. Tratar 5xx como
recusa é o erro que autoriza uma segunda tentativa e toca o telefone duas vezes.

3xx pela mesma razão: com `follow_redirects=False` o redirect chega sem ter sido
seguido, e um redirect inesperado num endpoint de escrita não é sucesso nem
recusa.

A regra é conservadora por construção: só afirmamos "não saiu" quando dá para
provar. Em TODOS os casos, zero retry automático.

Segredo e PII
-------------
O token sai de `SecretStr` apenas no ponto exato em que o cabeçalho é montado,
e o cabeçalho é `Authorization: <token>`, **sem `Bearer`** — confirmado com o
fornecedor e por teste empírico.

As exceções guardam no máximo um `status_code`. Nenhuma guarda `Response` ou
`Request`: o objeto do httpx carrega os cabeçalhos por referência, e uma
exceção que o segurasse levaria o `Authorization` para dentro de qualquer
traceback. Pelo mesmo motivo a tradução usa `from None` — encadear a exceção
original a penduraria no `__cause__`.

E `metadata` é exatamente `{"gateway": "HelpHS"}`, sem parâmetro que permita
acrescentar nada. Não é excesso de zelo: duas integrações desta conta no
fornecedor estão **sem filtro** (`webhookConstraint` nulo e `{}`), e se
constraint vazia significar "sem filtro", os webhooks das nossas chamadas serão
entregues a endpoints de outros sistemas da empresa. Enquanto isso não for
resolvido, o `metadata` não carrega nome, e-mail, documento, telefone nem texto
de chamado. A chave `gateway` também é o que o `webhookConstraint` da nossa
integração vai filtrar: grafia divergente faz a entrega parar em silêncio.
"""

from dataclasses import dataclass

import httpx

from app.core.config import get_settings

# O valor que o `webhookConstraint` da nossa integração filtra. Constante, e não
# literal solto, porque a mesma grafia precisa aparecer aqui e no cadastro da
# integração no fornecedor — e divergir entre os dois não levanta erro nenhum,
# só faz o webhook nunca chegar.
GATEWAY = "HelpHS"


class Api4ComDesligadaError(RuntimeError):
    """A integração está desligada: `API4COM_ENABLED` é falso."""


class Api4ComIndisponivelError(RuntimeError):
    """Não houve comunicação HTTP útil com o fornecedor.

    A conexão falhou antes de a requisição ser escrita, então não houve efeito
    do nosso lado da conversa. É a única categoria, junto da flag desligada, em
    que oferecer nova tentativa é seguro — e ainda assim a decisão é de quem
    chamar, nunca deste módulo.
    """


class Api4ComRecusadaError(RuntimeError):
    """O fornecedor respondeu rejeitando a requisição. SÓ 4xx.

    A afirmação é sobre a REQUISIÇÃO, não sobre o telefone: sabemos que ele
    respondeu recusando. 5xx NÃO entra aqui — ver a tabela no topo do módulo.
    """

    def __init__(self, status_code: int) -> None:
        # Só o número. O corpo da resposta e os cabeçalhos ficam de fora para
        # que nem a mensagem nem o traceback possam carregar `Authorization`.
        super().__init__(f"a API4COM rejeitou a requisição (HTTP {status_code})")
        self.status_code = status_code


class Api4ComResultadoIndeterminadoError(RuntimeError):
    """Não dá para provar que a ligação não saiu. Ela PODE estar tocando.

    Leva 5xx, 3xx, erro de transporte depois da conexão e 2xx com corpo
    ilegível. Quem tratar isto não pode repetir a chamada automaticamente, e
    deve dizer à pessoa que a ligação talvez esteja a caminho.

    Não guarda atributo nenhum — o status, quando existe, vai no texto.
    """


@dataclass(frozen=True)
class Api4ComCreateCallResult:
    """O que o fornecedor devolveu, sem interpretação.

    Não há campo para o identificador da chamada porque o schema da resposta de
    `POST /calls` **não está confirmado**: a documentação não o define e a sonda
    classifica a pergunta como NÃO DETERMINADO. Inventar `id`, `call_id` ou
    `data.id` aqui criaria um contrato que o fornecedor não prometeu. A Fase 2B
    segue bloqueada até haver evidência, e é ela quem acrescenta o campo.
    """

    status_code: int
    payload: object | None


def _url_das_chamadas(base_url: str) -> str:
    """Junta a base com `/calls` sem depender de o painel ter acertado a barra.

    Só junção estrutural: nada do payload passa por aqui.
    """
    return f"{base_url.rstrip('/')}/calls"


async def create_call(*, caller: str, called: str, extension: str) -> Api4ComCreateCallResult:
    """Pede ao fornecedor que inicie uma ligação. NÃO repete em nenhuma hipótese.

    Os três argumentos são repassados como chegaram. Este módulo não conhece
    DDD, não acrescenta nem remove `+55` e não valida grafia de número: o
    formato aceito em `called` segue em aberto com o fornecedor, e o transporte
    não é o lugar de adivinhá-lo.
    """
    settings = get_settings()

    # Antes de qualquer cliente HTTP: com a integração desligada não pode haver
    # socket, nem DNS, nem leitura do token.
    if not settings.api4com_enabled:
        raise Api4ComDesligadaError(
            "API4COM_ENABLED está desligada: nenhuma chamada é iniciada nesse estado"
        )

    corpo = {
        "caller": caller,
        "called": called,
        "extension": extension,
        "metadata": {"gateway": GATEWAY},
    }

    # `get_secret_value()` aparece uma única vez no módulo, e é aqui. Sem
    # `Bearer`: a API4COM recebe o token cru.
    cabecalhos = {"Authorization": settings.api4com_token.get_secret_value()}

    # `retries=0` explícito, mesmo sendo o default: é a linha que um teste
    # consegue prender e que o próximo leitor consegue ver.
    transporte = httpx.AsyncHTTPTransport(retries=0)

    try:
        async with httpx.AsyncClient(
            timeout=settings.api4com_timeout_seconds,
            transport=transporte,
            follow_redirects=False,
        ) as cliente:
            resposta = await cliente.post(
                _url_das_chamadas(settings.api4com_base_url),
                headers=cabecalhos,
                json=corpo,
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        # Aperto de mão TCP/TLS: a requisição não chegou a ser escrita, então
        # não houve comunicação HTTP útil com o fornecedor.
        raise Api4ComIndisponivelError(
            "não foi possível falar com a API4COM: não houve comunicação com o fornecedor"
        ) from None
    except httpx.TransportError:
        # Tudo o mais — leitura, escrita, protocolo, pool. A requisição pode ter
        # saído, e não há como provar que não.
        raise Api4ComResultadoIndeterminadoError(
            "a API4COM não respondeu a tempo: a chamada pode ter sido iniciada"
        ) from None

    codigo = resposta.status_code

    # 4xx é o ÚNICO caso em que o fornecedor nos diz que rejeitou a requisição.
    # E mesmo aqui a afirmação é sobre a REQUISIÇÃO, não sobre o telefone: o
    # que sabemos é que ele respondeu recusando, e é só isso que a mensagem diz.
    if 400 <= codigo < 500:
        raise Api4ComRecusadaError(codigo)

    # 5xx NÃO prova que a chamada não saiu. O fornecedor pode ter recebido o
    # POST, disparado a ligação e só depois quebrado por dentro — o 500 descreve
    # o estado do servidor dele, não o do telefone de quem ia receber.
    #
    # 3xx também não: com `follow_redirects=False` o redirect chega aqui sem ter
    # sido seguido, e um redirect inesperado num endpoint de escrita não é nem
    # sucesso nem recusa. Pode ter havido efeito antes.
    #
    # Os dois vão para indeterminado pela mesma regra conservadora do resto do
    # módulo: só afirmamos "não saiu" quando dá para provar.
    if not 200 <= codigo < 300:
        raise Api4ComResultadoIndeterminadoError(
            f"a API4COM respondeu HTTP {codigo}: a chamada pode ter sido iniciada"
        )

    if not resposta.content:
        return Api4ComCreateCallResult(status_code=resposta.status_code, payload=None)

    try:
        payload = resposta.json()
    except ValueError:
        # Respondeu 2xx com um corpo que não se lê. Provavelmente criou a
        # chamada; não dá para afirmar. Vale a regra conservadora.
        raise Api4ComResultadoIndeterminadoError(
            "a API4COM respondeu com um corpo ilegível: a chamada pode ter sido iniciada"
        ) from None

    return Api4ComCreateCallResult(status_code=resposta.status_code, payload=payload)
