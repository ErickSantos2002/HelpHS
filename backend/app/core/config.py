import json
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Os dois modos da Helô. Constantes, e não literais soltos, porque o valor é
# comparado em dois lugares — aqui, ao ler o painel, e em `helo.py`, ao decidir
# o turno —, e uma grafia divergente entre os dois cairia calada em triagem.
HELO_MODO_TRIAGEM = "triagem"
HELO_MODO_COMPLETA = "completa"

# Nomes e endereços que só existem na máquina de quem desenvolve. Comparar o
# HOST da URL com este conjunto — e não procurar "localhost" no texto — evita os
# dois erros: barrar um domínio legítimo que contenha a palavra (ex.:
# localhost.healthsafetytech.com) e deixar passar [::1] ou 0.0.0.0.
_HOSTS_LOCAIS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", ""})


_FORMATOS_DE_CALLED = frozenset({"nacional", "e164"})


class ConfiguracaoDaTelefoniaInvalidaError(RuntimeError):
    """A telefonia está ligada com configuração que não permite operar.

    ⚠️ NÃO herda de `ValueError`, e essa é a única razão de a classe existir.

    Todas as outras validações deste arquivo levantam `ValueError` de dentro do
    `model_post_init`, e o pydantic as embrulha num `ValidationError` — que
    imprime, junto da mensagem, um `input_value=` com o dicionário de entrada
    truncado. MEDIDO no pydantic 2.11.3: com `API4COM_TOKEN` vindo do ambiente
    e outra validação falhando, a mensagem do `ValidationError` traz a CAUDA do
    token. O segredo inteiro não sai, mas 22 caracteres finais saem — e vão
    para o log de boot, que é lido por mais gente do que o painel.

    Exceção que não seja `ValueError` nem `AssertionError` o pydantic deixa
    subir intacta, com a nossa mensagem e nada mais. É o que esta faz.

    Consequência para quem lê: `pytest.raises(ValueError)` NÃO pega esta. Os
    testes da telefonia em `tests/test_config.py` esperam esta classe pelo
    nome, de propósito.
    """


# ── STARTTLS e o CVE-2026-55558 ───────────────────────────────
#
# O `aiosmtplib` abaixo da 5.1.2 não descarta o que ficou no buffer de recepção
# antes do handshake do STARTTLS. Bytes lidos do socket em TEXTO CLARO
# sobrevivem à fronteira e são interpretados como se tivessem chegado dentro do
# TLS — um atacante ativo na perna em claro injeta respostas na sessão.
#
# O aviso afeta SÓ quem faz o upgrade por STARTTLS. Com TLS implícito (porta
# 465) não existe perna em claro, e o caminho vulnerável nunca é percorrido.
#
# A correção pelo pacote exige `aiosmtplib >= 5.1.2`, hoje travado pelo
# `fastapi-mail <4.0.0`. Até isso destravar, a mitigação é de configuração — e
# a guarda em `_valida_producao` existe para que ela não dependa de alguém
# lembrar de manter a variável certa no painel.
_AIOSMTPLIB_CORRIGIDO = (5, 1, 2)


def _aiosmtplib_vulneravel() -> bool:
    """True se a versão instalada estiver abaixo da que corrige o CVE.

    Lê a versão real do ambiente em vez de olhar o `requirements.txt`: o que
    importa é o que está rodando, não o que está escrito.
    """
    try:
        from importlib.metadata import version

        bruta = version("aiosmtplib")
    except Exception:  # noqa: BLE001 — pacote ausente: sem envio, sem risco
        return False

    numeros = []
    for parte in bruta.split(".")[:3]:
        digitos = "".join(c for c in parte if c.isdigit())
        numeros.append(int(digitos) if digitos else 0)
    while len(numeros) < 3:
        numeros.append(0)
    return tuple(numeros) < _AIOSMTPLIB_CORRIGIDO


# APP_ENV vem digitado à mão no painel de deploy: "Production" e "prod" precisam
# valer como produção, senão um detalhe de caixa desliga TODAS as validações.
#
# A tolerância mora no próprio campo (ver `_normaliza_app_env`), não em cada
# leitura: enquanto estava só aqui, `is_development` e o rate limiter
# comparavam a string crua — `APP_ENV=Testing` num job de CI subia o limiter
# ligado contra um Redis inexistente, e `Development` desligava o /docs calado.
_NOMES_DE_PRODUCAO = frozenset({"production", "prod"})


def _host_de(url: str) -> str:
    """Host da URL, em minúsculas. Aceita valor sem esquema (`localhost:5173`)."""
    referencia = url if "//" in url else f"//{url}"
    return (urlparse(referencia).hostname or "").lower()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "development"

    @field_validator("app_env")
    @classmethod
    def _normaliza_app_env(cls, valor: str) -> str:
        """Ponto único onde a caixa e o espaço do APP_ENV deixam de importar."""
        return valor.strip().lower()

    # Senha do admin criado por `app.seeds`, que o `start.sh` roda a cada boot.
    # Sem default de propósito: enquanto havia um literal no código, todo deploy
    # de produção criava um administrador ativo com senha publicada no
    # repositório. Ausente, o seed pula a criação em vez de cair num valor
    # conhecido — e é essa ausência, não o APP_ENV, que segura o caso de a
    # variável de ambiente estar errada.
    seed_admin_password: str | None = None

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://localhost:8000"

    def get_cors_origins(self) -> list[str]:
        v = self.cors_origins.strip()
        if v.startswith("["):
            try:
                carregado = json.loads(v)
            except json.JSONDecodeError as exc:
                # Sem isto o boot morre com um JSONDecodeError que não diz qual
                # variável está malformada
                raise ValueError(f"CORS_ORIGINS não é um JSON válido: {exc}") from exc
            return [str(o).strip() for o in carregado if str(o).strip()]
        return [o.strip() for o in v.split(",") if o.strip()]

    # Database
    database_url: str
    postgres_user: str = "helpdesk_user"
    postgres_password: str = ""
    postgres_db: str = "helpdesk_db"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    # JWT — suporta conteudo direto (producao) ou caminho de arquivo (dev)
    jwt_private_key_path: str = "./keys/private.pem"
    jwt_public_key_path: str = "./keys/public.pem"
    jwt_private_key: str = ""  # conteudo PEM direto (prioridade sobre path)
    jwt_public_key: str = ""  # conteudo PEM direto (prioridade sobre path)
    jwt_access_token_expires_minutes: int = 480
    jwt_refresh_token_expires_days: int = 7
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "helpdesk.healthsafetytech.com"

    # Segundo fator (TOTP) — chave da cifra do segredo, 32 bytes em base64
    # urlsafe. Nasce vazia e NÃO tem default: uma chave embutida no repositório
    # cifraria sem proteger nada. Vazia, o segundo fator fica indisponível e o
    # login segue como sempre foi — nenhum boot é derrubado por causa dela.
    mfa_secret_encryption_key: str = ""

    def get_private_key(self) -> str:
        if self.jwt_private_key:
            return self.jwt_private_key.replace("\\n", "\n")
        with open(self.jwt_private_key_path) as f:
            return f.read()

    def get_public_key(self) -> str:
        if self.jwt_public_key:
            return self.jwt_public_key.replace("\\n", "\n")
        with open(self.jwt_public_key_path) as f:
            return f.read()

    # Security
    secret_key: str = ""
    bcrypt_rounds: int = 12

    def model_post_init(self, __context: Any) -> None:
        # ⚠️ A API4COM é validada AQUI, no topo, e essa posição é o requisito —
        # não estilo. Tudo o que vem depois do `return` abaixo é pulado em
        # development e testing; a telefonia não pode ser pulada.
        #
        # A razão da divergência: as validações de baixo protegem contra subir
        # PRODUÇÃO com valor de desenvolvimento, e em dev esse valor é o certo.
        # Esta protege contra ligar a integração sem ter como autenticar — e
        # isso está igualmente errado em qualquer ambiente. Quem ligar a flag
        # em dev sem token merece descobrir na subida, não numa falha confusa
        # no primeiro uso.
        self._valida_api4com()

        # A lista do que ESCAPA é fechada, e é essa a diferença. Enquanto a
        # condição era `if not self.is_production`, qualquer APP_ENV fora de
        # "production"/"prod" passava batido: um staging publicado na internet
        # aceitava SECRET_KEY curta, CORS_ORIGINS=* e FRONTEND_URL de
        # localhost — e staging é justamente onde se testa com dado copiado do
        # real. Agora só desenvolvimento e teste ficam de fora; um APP_ENV
        # desconhecido cai no lado severo, que é o lado seguro do erro.
        #
        # Apertar a validação não promove o ambiente: `is_production` continua
        # False para staging, senão ele herdaria decisões que são só de
        # produção — o /docs desligado, o seed de admin que não roda.
        if self.is_development or self.is_testing:
            return

        if len(self.secret_key) < 32:
            raise ValueError(f"SECRET_KEY precisa ter ao menos 32 caracteres em '{self.app_env}'")

        # O default de cors_origins é localhost. Como o nginx do front não faz
        # proxy para a API, o navegador fala com outro domínio e o CORS é
        # obrigatório: subir com o default deixaria o front bloqueado, e "*"
        # abriria a API para qualquer site. Falhar no boot é melhor do que
        # descobrir isso em produção — mesma escolha feita para a SECRET_KEY.
        origens = self.get_cors_origins()
        if not origens:
            raise ValueError(
                f"CORS_ORIGINS está vazio em '{self.app_env}': defina o domínio real do front"
            )
        if any(o == "*" for o in origens):
            raise ValueError(
                f"CORS_ORIGINS não pode ser '*' em '{self.app_env}': use o domínio do front"
            )
        locais = [o for o in origens if _host_de(o) in _HOSTS_LOCAIS]
        if locais:
            raise ValueError(
                "CORS_ORIGINS precisa ser definido com o domínio real do front "
                f"(estas origens são locais: {', '.join(locais)})"
            )

        # Mesma classe de falha, outro efeito: FRONTEND_URL monta os links dos
        # e-mails de confirmação e de redefinição de senha. Apontando para
        # localhost em produção, o e-mail sai com um link que não abre para
        # ninguém — e nada no backend reclama.
        if _host_de(self.frontend_url) in _HOSTS_LOCAIS:
            raise ValueError(
                "FRONTEND_URL precisa ser o endereço público do sistema: "
                "os links dos e-mails de confirmação e de senha saem a partir dele"
            )

        # Adotar a confirmação de e-mail sem ter como enviar e-mail é a
        # armadilha que travou login em produção: conta nasce não-verificada e
        # a mensagem de confirmação nunca sai.
        if self.email_verification_enabled and not self.email_is_configured():
            raise ValueError(
                "EMAIL_VERIFICATION_ENABLED=true exige SMTP configurado "
                "(SMTP_USER/SMTP_FROM_EMAIL): sem ele, contas novas ficariam "
                "presas esperando um e-mail que nunca chega"
            )

        # ── STARTTLS vulnerável (CVE-2026-55558) ──────────────────
        #
        # Só vale quando há envio configurado: SMTP desligado não tem risco de
        # transporte e não pode travar o boot por causa disso.
        if self.email_is_configured():
            if self.smtp_tls and self.smtp_ssl:
                raise ValueError(
                    "SMTP_TLS e SMTP_SSL não podem estar ligados ao mesmo tempo: "
                    "STARTTLS (587) e TLS implícito (465) são caminhos "
                    "excludentes, e ligar os dois esconde qual está em uso"
                )
            if self.smtp_tls and not self.smtp_ssl and _aiosmtplib_vulneravel():
                raise ValueError(
                    "STARTTLS com aiosmtplib vulnerável não é permitido em "
                    "produção. Use TLS implícito na porta 465 "
                    "(SMTP_SSL=true, SMTP_TLS=false, SMTP_PORT=465) ou "
                    "atualize aiosmtplib para versão corrigida (>= 5.1.2). "
                    "Motivo: CVE-2026-55558 — bytes lidos em texto claro "
                    "sobrevivem ao handshake do STARTTLS e são interpretados "
                    "como se tivessem chegado dentro do TLS."
                )

        # Por último de propósito: as validações acima protegem a subida de
        # quebras que já existiam, e cada teste delas espera o PRÓPRIO erro.
        if self.lgpd_revisao_politica is None:
            raise ValueError(
                f"LGPD_REVISAO_POLITICA está vazio em '{self.app_env}': defina a "
                "revisão vigente da Política de Privacidade (ex.: 00). Sem ela, "
                "cada aceite seria gravado sem dizer qual texto foi aceito"
            )

    # Armazenamento de arquivos (anexos e avatares) em disco.
    # No deploy, este caminho precisa ser um volume — sem isso os arquivos
    # somem a cada redeploy do container.
    upload_dir: str = "/app/uploads"
    # Validade do link temporario devolvido para baixar/exibir um arquivo
    file_url_expires_seconds: int = 3600

    # MinIO — mantido apenas para compatibilidade de configuracao; o
    # armazenamento passou a ser em disco (ver upload_dir)
    minio_endpoint: str = "localhost"
    minio_port: int = 9000
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket_name: str = "helpdesk-attachments"
    minio_use_ssl: bool = False

    # LLM
    #
    # Interruptor da IA. Ligado por padrão: desligar por padrão apagaria a
    # classificação automática em produção no deploy seguinte, sem ninguém
    # pedir — e mudança de comportamento silenciosa é o oposto do que uma flag
    # de emergência deve fazer.
    #
    # Existe porque, até então, a única forma de parar de mandar conteúdo de
    # chamado para fora era APAGAR a chave do painel: uma manobra que também
    # destrói a configuração e que ninguém desfaz sem ter a chave de novo. Com
    # a flag, desligar é reversível.
    llm_enabled: bool = True

    # Interruptor SÓ da Helô — o atendimento por IA que fala com o cliente.
    #
    # Separado do `llm_enabled` de propósito: desligar a Helô num dia ruim não
    # pode apagar junto a classificação automática e o "melhorar redação", que
    # são ferramentas do técnico e ninguém pediu para tirar. Quem quiser cortar
    # tudo continua tendo o `LLM_ENABLED`.
    #
    # DESLIGADA por padrão, ao contrário do `llm_enabled`, e pelo mesmo
    # raciocínio invertido: aqui a mudança silenciosa seria a IA começar a
    # FALAR COM O CLIENTE no deploy seguinte, sem ninguém ter pedido. Ligar é
    # decisão, não default.
    helo_enabled: bool = False

    # O que a Helô faz quando está ligada — e é ORTOGONAL ao `helo_enabled`:
    # desligada é desligada em qualquer modo.
    #
    # `triagem` é a recepcionista da Fase 1: saudação, encerramento e escalada,
    # sem embedding e sem LLM. `completa` é a Fase 2, que busca na Base de
    # Conhecimento e responde com o modelo.
    #
    # Existe porque a Fase 2 com a base vazia escala toda pergunta, e os
    # manuais técnicos dos sete aparelhos estão sendo reescritos. O gatilho para
    # virar está em `docs/decisoes-e-regras.md`.
    #
    # TRIAGEM por padrão, e também quando o valor não se reconhece. O modo
    # seguro é o que o sistema assume quando não sabe — e a alternativa que foi
    # recusada é usar a AUSÊNCIA da `DEEPSEEK_API_KEY` como standby: no dia em
    # que alguém preenchesse a chave para testar outra coisa, ela acordaria
    # sozinha, com a base vazia, falando com cliente.
    helo_modo: str = HELO_MODO_TRIAGEM

    @field_validator("helo_modo")
    @classmethod
    def _modo_da_helo_seguro(cls, valor: str) -> str:
        """
        Só `completa` acorda a Fase 2; todo o resto é triagem.

        Caixa e espaço não importam, no mesmo idioma do `APP_ENV`. Um valor
        preenchido e não reconhecido deixa aviso no log com o que veio: cair em
        triagem calado deixaria quem configurou achando que ela acordou — e o
        erro de digitação provável, `completo`, é justamente esse.
        """
        limpo = valor.strip().lower()
        if limpo == HELO_MODO_COMPLETA:
            return HELO_MODO_COMPLETA
        if limpo not in ("", HELO_MODO_TRIAGEM):
            logger.warning(
                f"HELO_MODO={valor!r} não é um modo conhecido "
                f"({HELO_MODO_TRIAGEM!r} ou {HELO_MODO_COMPLETA!r}); a Helô fica em triagem"
            )
        return HELO_MODO_TRIAGEM

    # O serviço de embedding da Helô — um contêiner PRÓPRIO, não uma biblioteca
    # dentro desta API.
    #
    # A separação não é preferência de arquitetura: é consequência de um número
    # medido. O backend roda com `--workers 1` (`start.sh:40`), e trabalho de
    # CPU síncrono no event loop congela a API para TODO MUNDO. Já aconteceu e
    # está registrado — uma requisição pesada ocupou o processo por 151
    # segundos (`mudanças.md:50`). Calcular embedding aqui dentro seria repetir
    # esse defeito de propósito, a cada turno de conversa da Helô.
    #
    # Nasce VAZIA. Sem URL, o cliente devolve None em silêncio, a busca não
    # acontece e a Helô escala — exatamente como já faz sem a chave da
    # DeepSeek. Ligar é decisão, não default.
    helo_embedding_url: str = ""

    # Curto de propósito, e bem menor que os 30 s do LLM. Um embedding leva
    # centenas de milissegundos; se está demorando dez, o serviço tem problema,
    # e prender o cliente esperando não melhora nada — escalar logo é resposta
    # melhor do que uma espera longa seguida da mesma escalada.
    helo_embedding_timeout_seconds: int = 10

    # De quanto em quanto tempo a varredura procura artigo publicado novo ou
    # editado para indexar (`app/services/helo_indexacao.py`). Cinco minutos é
    # a latência entre publicar e a Helô passar a usar o texto — só para texto
    # novo: despublicar tem efeito imediato, porque a busca filtra ao vivo.
    # Zero desliga a varredura.
    helo_indexacao_intervalo_segundos: int = 300

    # DeepSeek — o único provedor de LLM.
    #
    # Nasce VAZIA: a chave vive no painel do EasyPanel, nunca no repositório, e
    # a IA só é ligada depois do documento de LGPD publicado no cadastro. Sem
    # chave, o `llm.py` devolve None em silêncio — é o comportamento de hoje em
    # produção e é o que segura o sistema com a IA desligada.
    deepseek_api_key: str = ""

    # ⚠️ O endpoint e o nome do modelo abaixo NÃO foram conferidos contra a
    # documentação oficial da DeepSeek. São CONFIGURAÇÃO com padrão, e não
    # constante no código, justamente por isso: quando a chave chegar e o teste
    # contra o serviço real disser outra coisa, o conserto é no painel, sem
    # tocar em código e sem deploy.
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # Vale para as quatro chamadas. Era `openai_temperature`, com o mesmo 0.3.
    llm_temperature: float = 0.3
    llm_request_timeout_seconds: int = 30

    # ── Telefonia — API4COM ───────────────────────────────────
    #
    # DESLIGADA por padrão, pelo mesmo raciocínio do `helo_enabled`: ligar
    # sozinha faria o sistema DISCAR PARA O TELEFONE DE UMA PESSOA no deploy
    # seguinte, sem ninguém ter pedido. Ligar é decisão.
    #
    # Na Fase 2A não existe consumidor: nenhum router, lifespan ou laço de
    # fundo importa `services/api4com.py`. A flag existe desde já porque a
    # validação de boot abaixo precisa de um interruptor para guardar.
    api4com_enabled: bool = False

    # CONFIGURAÇÃO com padrão, não constante no código — mesmo critério do
    # `deepseek_base_url`: se o fornecedor mudar o endereço, o conserto é no
    # painel, sem tocar em código e sem deploy. É o endereço que a sonda já
    # exercita.
    api4com_base_url: str = "https://api.api4com.com/api/v1"

    # ⚠️ ÚNICO segredo do projeto declarado como `SecretStr`, e é divergência
    # deliberada do resto do arquivo.
    #
    # Todos os outros (`smtp_password`, `deepseek_api_key`,
    # `mfa_secret_encryption_key`) são `str` cru. Isso significa que
    # `repr(settings)`, `settings.model_dump()` e `model_dump_json()` imprimem
    # os três por extenso — o que segura hoje é disciplina de quem escreve log,
    # não o tipo. Segredo NOVO não precisa nascer com essa dívida: com
    # `SecretStr`, o vazamento passa a exigir um `get_secret_value()` explícito,
    # que é greppável e aparece em revisão.
    #
    # O custo é que ler o valor tem cerimônia. Ele é lido em UM lugar só, na
    # montagem do `Authorization` em `services/api4com.py`.
    api4com_token: SecretStr = SecretStr("")

    api4com_timeout_seconds: int = 15

    # ── Orquestração da tentativa (Fase 2C.2) ────────────────
    #
    # O lock cobre a janela inteira entre validar e terminar a conversa com o
    # fornecedor. 30s é o teto da chamada (15s) com folga: um processo que
    # morra segurando o lock libera sozinho, e ninguém fica preso.
    api4com_lock_ttl_seconds: int = 30
    # ⚠️ Aqui morava `api4com_repeat_window_seconds`, a janela de 5 minutos da
    # antirrepetição. Saiu em 25/09/2026 junto com a regra que a lia: quem
    # atende liga quantas vezes for preciso. `extra="ignore"` no `model_config`
    # garante que um `API4COM_REPEAT_WINDOW_SECONDS` esquecido no painel não
    # derruba o boot — ele passa a ser apenas ignorado.
    # Teto por hora, POR ATOR. Não substitui o lock: o lock impede
    # simultaneidade, isto impede volume. Chave autenticada, nunca IP — atrás do
    # proxy do EasyPanel o IP junta a empresa inteira num balde só.
    #
    # ⚠️ Aqui morava também `api4com_calls_per_ticket_per_hour = 3`, o teto por
    # CHAMADO. Saiu em 25/09/2026: ele limitava quantas vezes se liga para o
    # mesmo chamado, e a regra passou a ser "quantas vezes for preciso". O teto
    # por ator cobre o risco que motivou os dois — laço, conta comprometida e
    # volume anormal são propriedades de quem liga.
    #
    # `extra="ignore"` no `model_config` garante que um
    # `API4COM_CALLS_PER_TICKET_PER_HOUR` esquecido no painel seja apenas
    # ignorado, sem derrubar o boot.
    api4com_calls_per_actor_per_hour: int = 20

    # ── Formato de `called` no POST /calls (Fase 2C.3) ───────
    #
    # ⚠️ DECISÃO EM ABERTO COM O FORNECEDOR. A documentação oficial mostra as
    # DUAS grafias para a MESMA rota e o MESMO campo:
    #
    #   referência da API (Call.clickToCall)  ->  "called": "4833328530"
    #   guia do webphone próprio              ->  "called": "+554833328530"
    #
    # Medido em 24/09/2026 nas duas páginas. Não é o caso do `/dialer`, que é
    # rota morta e usa outro campo (`phone`) — essa separação já estava escrita
    # em `docs/decisoes-e-regras.md` e está INCOMPLETA: o `+55` aparece também
    # no `/calls`.
    #
    # O padrão segue a REFERÊNCIA da API, por ser a especificação da rota e não
    # um exemplo de tutorial. Mas é escolha de moeda, não conclusão: trocar é
    # mudar esta variável, sem tocar em código. Enquanto `API4COM_ENABLED` for
    # falso, a escolha não produz efeito nenhum.
    #
    #   nacional -> 4833328530     (tira o +55 de um E.164 brasileiro)
    #   e164     -> +554833328530  (manda o canônico interno como está)
    api4com_called_format: str = "nacional"

    def _valida_api4com(self) -> None:
        """Desligada, nada é exigido. Ligada, o que falta impede a subida.

        As mensagens citam o NOME da variável e mais nada: nunca o valor do
        token, nunca o `Settings` inteiro. Quem lê um log de boot que falhou
        não deveria ganhar de brinde a credencial que faltava.
        """
        if not self.api4com_enabled:
            return

        if not self.api4com_token.get_secret_value().strip():
            raise ConfiguracaoDaTelefoniaInvalidaError(
                "API4COM_ENABLED=true exige API4COM_TOKEN preenchido: "
                "sem credencial nenhuma chamada seria autenticada"
            )

        endereco = urlparse(self.api4com_base_url.strip())
        if endereco.scheme not in {"http", "https"} or not endereco.netloc:
            raise ConfiguracaoDaTelefoniaInvalidaError(
                "API4COM_BASE_URL precisa ser uma URL http(s) completa "
                "(exemplo: https://api.api4com.com/api/v1)"
            )

        if self.api4com_timeout_seconds <= 0:
            raise ConfiguracaoDaTelefoniaInvalidaError(
                "API4COM_TIMEOUT_SECONDS precisa ser maior que zero: "
                "iniciar ligação sem teto de espera prenderia a requisição"
            )

        # Validado com a integração LIGADA: um valor desconhecido aqui faria
        # cada ligação sair com o telefone numa grafia que ninguém escolheu.
        if self.api4com_called_format not in _FORMATOS_DE_CALLED:
            raise ConfiguracaoDaTelefoniaInvalidaError(
                "API4COM_CALLED_FORMAT precisa ser um de "
                f"{sorted(_FORMATOS_DE_CALLED)} — veja o comentário do campo"
            )

    # Email
    smtp_host: str = "smtp.gmail.com"
    # TLS implícito (465), e não STARTTLS (587) — ver `_aiosmtplib_vulneravel`
    # e o CVE-2026-55558 no topo deste arquivo. O padrão precisa ser o caminho
    # seguro: quem herdar a configuração sem ler nada não deve cair no
    # vulnerável por omissão.
    smtp_port: int = 465
    smtp_tls: bool = False
    smtp_ssl: bool = True
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "Help Desk Health & Safety"
    smtp_from_email: str = ""
    # Para onde vão as respostas de quem responder um e-mail automático.
    # Vazio = as respostas caem na própria caixa de disparo, que ninguém lê.
    smtp_reply_to: str = ""

    # Endereço público do sistema — usado para montar os links dos e-mails
    frontend_url: str = "http://localhost:5173"

    # Confirmação de e-mail no cadastro
    # A exigência é ADOTADA por esta flag, não deduzida das variáveis de SMTP:
    # a inferência já travou login em produção — SMTP_USER/SMTP_FROM_EMAIL
    # preenchidos (seed do .env.example) ligavam a confirmação sem SMTP
    # funcional, a conta nascia não-verificada e o e-mail nunca saía.
    email_verification_enabled: bool = False
    email_verification_token_hours: int = 24
    password_reset_token_hours: int = 1

    # LGPD — a revisão VIGENTE dos documentos que o cadastro pede para aceitar
    #
    # Declarada, não consultada: publicar revisão nova é evento raro e manual,
    # do mesmo tipo do deploy, e cada aceite grava estes valores em
    # `lgpd_consents`. É isso que permite provar QUAL texto cada pessoa aceitou
    # (seção 15 da Política de Privacidade). Desenho em
    # `docs/superpowers/specs/2026-08-31-registro-da-revisao-aceita-design.md`.
    #
    # A da política é OBRIGATÓRIA fora de desenvolvimento e teste (ver o fim do
    # `model_post_init`): aceite sem revisão é exatamente o estado que a tabela
    # existe para acabar. A dos Termos de Uso é opcional porque o documento
    # ainda não existe — vazia, o aceite grava NULL, que é a verdade.
    lgpd_revisao_politica: str | None = None
    lgpd_revisao_termos: str | None = None
    # Liga a tela de re-aceite para clientes cuja última revisão aceita não é a
    # vigente. DESLIGADA por padrão: nenhum usuário anterior a esta mudança tem
    # histórico, e ligar antes do texto final faria todo cliente aceitar o
    # rascunho no primeiro login.
    lgpd_exige_reaceite: bool = False

    @field_validator("lgpd_revisao_politica", "lgpd_revisao_termos")
    @classmethod
    def _revisao_em_branco_e_ausente(cls, valor: str | None) -> str | None:
        # Variável criada no painel e deixada vazia é ausência, não a revisão "".
        if valor is None:
            return None
        return valor.strip() or None

    def email_is_configured(self) -> bool:
        """Só dá para exigir confirmação se houver como enviar o e-mail."""
        return bool(self.smtp_from_email or self.smtp_user)

    def requires_email_verification(self) -> bool:
        """
        Confirmação de e-mail só quando adotada de propósito E com SMTP
        presente. Sem a flag, variável de SMTP preenchida não muda nada; sem
        SMTP, ligar a flag sozinha também não — senão o cliente criaria conta
        e ficaria esperando um e-mail que nunca chega.
        """
        return self.email_verification_enabled and self.email_is_configured()

    # ClamAV
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_timeout_seconds: int = 30

    # Upload
    upload_max_file_size_mb: int = 25
    upload_max_files_per_ticket: int = 10
    upload_allowed_extensions: str = (
        ".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.gif,.txt,.csv,.zip,.rar"
    )

    # Encerramento do chamado (RN-005 / RN-006).
    # Os prazos são contados em DIAS ÚTEIS a partir do momento em que o chamado
    # foi resolvido — em dias corridos, quem resolvesse na sexta daria ao cliente
    # praticamente nenhum dia de trabalho para se manifestar.
    ticket_auto_close_business_days: int = 3
    ticket_reopen_business_days: int = 5
    # De quanto em quanto tempo a rotina de fechamento automático roda.
    # 0 desliga a rotina (útil em testes e em execução local).
    ticket_auto_close_interval_seconds: int = 3600

    # Logging
    log_level: str = "INFO"
    log_dir: str = "./logs"

    # Rate limiting — três chaves, uma por modelo de ameaça.
    #
    # Era uma só, reaproveitada em quatro endpoints de semânticas diferentes:
    # apertar o login para conter força bruta apertava junto o cadastro e o
    # "esqueci minha senha", e quem mexesse não teria como saber.
    #
    # Tentativa de credencial: alguém adivinhando senha ou código.
    rate_limit_login: str = "5/15minutes"
    # Ciclo de conta — cadastro, esqueci-a-senha, reenvio de confirmação. Cada
    # chamada dispara e-mail, então o limite protege a caixa alheia tanto quanto
    # o sistema.
    rate_limit_account: str = "5/15minutes"
    # Resgate de token vindo de link de e-mail. Mais folgado de propósito: quem
    # chega aqui já tem um token assinado nas mãos, e o caso comum é a pessoa
    # clicando de novo no link porque a primeira tentativa pareceu não responder.
    rate_limit_token: str = "10/15minutes"
    # Consulta de CNPJ e CEP em provedor externo. Chaveado por USUÁRIO, não por
    # IP (ver `chave_por_usuario`), porque o endpoint exige sessão.
    #
    # 30/hora é generoso de propósito. O gatilho no front é `onBlur` com o campo
    # completo — 14 dígitos de CNPJ, 8 de CEP —, então cada consulta custa um
    # ciclo de foco humano, e os dois únicos chamadores são formulários:
    # onboarding, que a pessoa faz uma vez, e edição de perfil. Uma sessão real
    # gasta 1 a 3 consultas; quem estiver corrigindo o número várias vezes chega
    # talvez a 10. O teto é umas dez vezes a sessão mais pesada que consigo
    # imaginar, e mesmo assim limita cada conta a 30 chamadas externas por hora
    # — antes do cache, que derruba esse número de novo.
    rate_limit_consulta_externa: str = "30/hour"

    # Quem pode falar pelos outros: lista de IPs/redes cujo X-Forwarded-For o
    # uvicorn aceita como sendo o IP real de quem chamou. O uvicorn lê esta
    # mesma variável do ambiente por conta própria — por isso o `start.sh` não
    # passa flag nenhuma, para não existirem duas fontes que podem divergir.
    #
    # O default do uvicorn é 127.0.0.1, ou seja, não confia em proxy nenhum.
    # Atrás do proxy do EasyPanel isso faz `get_remote_address` devolver o IP
    # do PRÓPRIO proxy, e o rate limit de login (5/15min) vira um balde único
    # para o sistema inteiro: cinco senhas erradas de qualquer pessoa travam o
    # login de todo mundo.
    #
    # Ligar resolve, MAS só é seguro se a porta do backend não estiver
    # publicada direto na internet — se estiver, qualquer um forja o
    # X-Forwarded-For e pula o rate limit por completo, que é pior do que o
    # balde global. Daí o default conservador: ligar é decisão de quem conhece
    # a topologia do deploy. Ver o aviso em mudanças.md.
    forwarded_allow_ips: str = ""

    @property
    def trusts_proxy_headers(self) -> bool:
        return bool(self.forwarded_allow_ips.strip())

    @property
    def rate_limit_por_ip_do_proxy(self) -> bool:
        """Produção sem proxy autorizado: o rate limit por IP é um balde só."""
        return self.is_production and not self.trusts_proxy_headers

    # As três leituras do ambiente ficam juntas e comparam o valor já
    # normalizado pelo `_normaliza_app_env` — nenhuma delas repete o strip/lower.

    @property
    def is_production(self) -> bool:
        return self.app_env in _NOMES_DE_PRODUCAO

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_testing(self) -> bool:
        return self.app_env == "testing"

    def openapi_url_efetiva(self) -> str | None:
        """
        Onde o spec da API é servido — `None` desliga a rota.

        Mesma condição do /docs e do /redoc de propósito: o spec É a
        documentação, em outro formato. Ter duas chaves para "expor a API por
        escrito" seria mais uma configuração para alguém deixar ligada sem
        querer, e a rodada passada já mostrou o que configuração esquecida
        custa.
        """
        return "/openapi.json" if self.is_development else None

    @property
    def allowed_extensions(self) -> list[str]:
        return [ext.strip() for ext in self.upload_allowed_extensions.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
