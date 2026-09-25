"""
O diagnóstico avulso de SMTP: `scripts/testa_smtp.py`.

Por que este arquivo existe
---------------------------
Em 25/09/2026, com o SMTP real já ativo em produção, o script rodou dentro do
contêiner e imprimiu `reply-to  : (vazio)` — enquanto a aplicação tinha
`SMTP_REPLY_TO` preenchido. O script mentiu.

A causa não era a configuração: era a lista branca `_CHAVES`. O fallback de
ambiente (o caminho que vale DENTRO do contêiner, onde não existe `.env`) copia
de `os.environ` só as chaves listadas nela — e `SMTP_REPLY_TO`, lido logo
adiante, nunca havia sido acrescentado. Com `.env` em disco o defeito não
aparece, porque ali o parser aceita toda linha `chave=valor`. Ou seja: o bug era
invisível na máquina de quem desenvolve e certeiro no único ambiente que o
script existe para diagnosticar.

Um script de diagnóstico que erra é pior que script nenhum: ele desvia a
investigação. Por isso a paridade com o `Settings` virou teste, e não comentário.

Por que a paridade NÃO é feita importando `get_settings()` no script
-------------------------------------------------------------------
Foi a correção mais óbvia, e ela quebraria o script. O docstring dele diz, com
razão, que usa `smtplib` puro e não passa pelo `Settings` nem pelo FastAPI-Mail
DE PROPÓSITO: ele é um oráculo independente. "Se ele entrega e a aplicação não,
o problema está na aplicação." Fazer os dois lados lerem a mesma fonte acaba com
o diagnóstico diferencial — um defeito no `Settings` passaria a fazer o script
mentir junto com a aplicação, que é exatamente o modo de falha que ele existe
para excluir.

Há um custo concreto além do teórico: `Settings.model_post_init` LEVANTA
exceção em vários cenários legítimos (guarda do CVE-2026-55558,
`LGPD_REVISAO_POLITICA` obrigatória fora de dev/test, validações da telefonia).
Um diagnóstico que morre por causa de LGPD é o diagnóstico que não serve na hora
do incêndio.

A paridade fica aqui, no teste: o script continua lendo o ambiente por conta
própria, e é ESTE arquivo que garante que a lista dele cobre os campos `smtp_*`
do `Settings`. A próxima chave nova é pega automaticamente, em vez de reaparecer
como este mesmo bug daqui a seis meses.

Nada aqui abre conexão SMTP, e nada aqui envia e-mail: todo teste para na
construção da mensagem ou antes dela. O `main()` — o único ponto que conecta —
não é chamado em nenhum teste deste arquivo.
"""

import pytest

from app.core.config import Settings
from scripts.testa_smtp import (
    _CHAVES,
    Configuracao,
    impressao_digital,
    le_configuracao,
    linhas_do_relatorio,
    monta_mensagem,
)

# Endereços de faz-de-conta. `.invalid` é reservado por RFC 2606 justamente
# para isto: não existe e não pode passar a existir.
_REPLY_TO = "suporte@exemplo.invalid"
_DESTINO = "destino@exemplo.invalid"
_SENHA = "re_uma_chave_de_faz_de_conta_1234567890"


def _ambiente_completo() -> dict[str, str]:
    """Um ambiente com TODAS as chaves preenchidas, como o do contêiner."""
    return {
        "SMTP_HOST": "smtp.exemplo.invalid",
        "SMTP_PORT": "2525",
        "SMTP_TLS": "true",
        "SMTP_SSL": "false",
        "SMTP_USER": "usuario",
        "SMTP_PASSWORD": _SENHA,
        "SMTP_FROM_NAME": "Nome Que Assina",
        "SMTP_FROM_EMAIL": "remetente@exemplo.invalid",
        "SMTP_REPLY_TO": _REPLY_TO,
    }


def _chaves_smtp_do_settings() -> set[str]:
    """As chaves que o script PRECISA conhecer, derivadas do `Settings`.

    Derivadas, não copiadas: campo novo em `Settings` entra aqui sem ninguém
    lembrar de editar teste.
    """
    return {nome.upper() for nome in Settings.model_fields if nome.startswith("smtp_")}


# ══════════════════════════════════════════════════════════════
# 1. A lista branca das variáveis de ambiente
# ══════════════════════════════════════════════════════════════


def test_reply_to_esta_na_lista_de_chaves_do_ambiente():
    """A regressão medida em 25/09/2026, em uma linha."""
    assert "SMTP_REPLY_TO" in _CHAVES


def test_as_chaves_do_script_cobrem_os_campos_smtp_do_settings():
    """Paridade: o que a aplicação configura, o diagnóstico tem de enxergar.

    Igualdade, não contenção, nos dois sentidos: chave a MENOS é o bug do
    reply-to de novo; chave a MAIS é o script prometendo diagnosticar uma
    configuração que a aplicação não tem.
    """
    assert set(_CHAVES) == _chaves_smtp_do_settings()


def test_a_paridade_pegaria_a_lista_de_antes_da_correcao():
    """Teste-dente: sem ele, o de cima poderia passar por construção.

    Estas são as oito chaves que o script tinha quando mentiu. Se a regra de
    paridade as aceitasse, ela não valeria nada.
    """
    lista_antiga = (
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_TLS",
        "SMTP_SSL",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_FROM_NAME",
        "SMTP_FROM_EMAIL",
    )
    assert set(lista_antiga) != _chaves_smtp_do_settings()


# ══════════════════════════════════════════════════════════════
# 2. Os padrões — o transporte que o script testa é o que a app usa
# ══════════════════════════════════════════════════════════════


def test_os_padroes_de_transporte_seguem_os_do_settings():
    """Porta, TLS e SSL omitidos têm de cair no MESMO caminho da aplicação.

    Divergir aqui é a mesma classe de mentira do reply-to, só mais grave: o
    script testaria STARTTLS na 587 enquanto a aplicação usa TLS implícito na
    465 — e a escolha da 465 no `Settings` é a mitigação do CVE-2026-55558, não
    preferência de estilo. Quem lesse "OK" teria testado outro transporte.

    Os valores esperados vêm do `Settings`, não literais, para que mudar o
    padrão da aplicação quebre este teste em vez de criar a divergência em
    silêncio.
    """
    cfg = le_configuracao({})

    assert cfg.porta == Settings.model_fields["smtp_port"].default
    assert cfg.usa_tls is Settings.model_fields["smtp_tls"].default
    assert cfg.usa_ssl is Settings.model_fields["smtp_ssl"].default


def test_o_script_nao_herda_o_host_padrao_do_settings():
    """Duas exclusões deliberadas da paridade, escritas para não parecerem
    esquecimento.

    `SMTP_HOST`: o `Settings` chuta `smtp.gmail.com`; o script se RECUSA a
    chutar host e sai com erro. Num diagnóstico, adivinhar o servidor é o pior
    padrão possível — testaria um provedor que ninguém configurou, e o "FALHA
    de conexao" resultante mandaria a investigação para o lado errado.

    `SMTP_FROM_NAME` fica fora por outro motivo, e sem asserção: ele só aparece
    no cabeçalho da mensagem de teste. Não muda credencial, transporte nem
    domínio — não muda o que o script prova. Alinhá-lo um dia é livre.
    """
    cfg = le_configuracao({})

    assert cfg.host == ""
    assert cfg.host != Settings.model_fields["smtp_host"].default


def test_o_ambiente_vence_os_padroes_em_todos_os_campos():
    """Nenhuma regressão de leitura: cada variável chega onde deve chegar."""
    cfg = le_configuracao(_ambiente_completo())

    assert cfg.host == "smtp.exemplo.invalid"
    assert cfg.porta == 2525
    assert cfg.usa_tls is True
    assert cfg.usa_ssl is False
    assert cfg.usuario == "usuario"
    assert cfg.senha == _SENHA
    assert cfg.nome == "Nome Que Assina"
    assert cfg.remetente == "remetente@exemplo.invalid"
    assert cfg.reply_to == _REPLY_TO


def test_sem_from_email_o_remetente_cai_no_usuario():
    """Comportamento antigo preservado: em muitos provedores os dois coincidem,
    e exigir o par completo travaria o diagnóstico sem motivo."""
    env = _ambiente_completo()
    del env["SMTP_FROM_EMAIL"]

    assert le_configuracao(env).remetente == "usuario"


@pytest.mark.parametrize("valor", ["TRUE", "True", "true"])
def test_a_leitura_dos_booleanos_ignora_caixa(valor):
    """O painel do EasyPanel não normaliza caixa, e quem digita, menos ainda."""
    env = _ambiente_completo()
    env["SMTP_SSL"] = valor

    assert le_configuracao(env).usa_ssl is True


# ══════════════════════════════════════════════════════════════
# 3. A mensagem — o Reply-To tem de sair no cabeçalho, não no relatório
# ══════════════════════════════════════════════════════════════


def test_a_mensagem_carrega_reply_to_quando_configurado():
    """O relatório dizer "CONFIGURADO" e o cabeçalho sair sem Reply-To seria
    uma mentira nova no lugar da antiga. O que prova a configuração é a
    mensagem, então é nela que se mede."""
    msg = monta_mensagem(le_configuracao(_ambiente_completo()), _DESTINO)

    assert msg["Reply-To"] == _REPLY_TO


def test_sem_reply_to_o_cabecalho_nao_existe():
    """Ausente é ausente: `Reply-To:` vazio é cabeçalho malformado, e alguns
    provedores recusam a mensagem por causa dele."""
    env = _ambiente_completo()
    del env["SMTP_REPLY_TO"]

    msg = monta_mensagem(le_configuracao(env), _DESTINO)

    assert "Reply-To" not in msg


def test_a_mensagem_sai_com_remetente_destino_e_assunto():
    cfg = le_configuracao(_ambiente_completo())
    msg = monta_mensagem(cfg, _DESTINO)

    assert msg["From"] == f"{cfg.nome} <{cfg.remetente}>"
    assert msg["To"] == _DESTINO
    assert "HelpHS" in msg["Subject"]
    assert msg.get_content_type() == "text/plain"


# ══════════════════════════════════════════════════════════════
# 4. O relatório — diagnostica sem virar vazamento
# ══════════════════════════════════════════════════════════════


def test_o_relatorio_diz_configurado_sem_revelar_o_reply_to():
    """O terminal costuma virar print no chat — o próprio script diz isso sobre
    a senha, e a razão vale igual para endereço. Para diagnosticar basta saber
    SE existe; qual é, quem precisar lê no painel."""
    linhas = linhas_do_relatorio(le_configuracao(_ambiente_completo()), _DESTINO, "teste")
    texto = "\n".join(linhas)

    assert "reply-to  : CONFIGURADO" in texto
    assert _REPLY_TO not in texto


def test_o_relatorio_diz_vazio_quando_nao_ha_reply_to():
    """Distinguir "não configurado" de "configurado" é o único trabalho desta
    linha — foi exatamente o que falhou em produção."""
    env = _ambiente_completo()
    del env["SMTP_REPLY_TO"]

    texto = "\n".join(linhas_do_relatorio(le_configuracao(env), _DESTINO, "teste"))

    assert "reply-to  : (vazio)" in texto
    assert "CONFIGURADO" not in texto


def test_a_senha_nunca_aparece_em_claro_no_relatorio():
    cfg = le_configuracao(_ambiente_completo())
    texto = "\n".join(linhas_do_relatorio(cfg, _DESTINO, "teste"))

    assert _SENHA not in texto
    assert impressao_digital(_SENHA) in texto


def test_o_relatorio_diz_a_origem_o_transporte_e_o_destino():
    """O destino sai inteiro de propósito: quem rodou o comando acabou de
    digitá-lo, e ver para quem o teste foi é parte do diagnóstico."""
    cfg = le_configuracao(_ambiente_completo())
    texto = "\n".join(linhas_do_relatorio(cfg, _DESTINO, "variaveis de ambiente"))

    assert "config de : variaveis de ambiente" in texto
    assert "smtp.exemplo.invalid:2525" in texto
    assert "ssl=False" in texto
    assert "starttls=True" in texto
    assert _DESTINO in texto


def test_a_configuracao_e_imutavel():
    """Ela atravessa relatório e mensagem; se alguém a ajustasse no meio, o
    relatório deixaria de descrever o que foi enviado."""
    cfg = le_configuracao(_ambiente_completo())

    with pytest.raises((AttributeError, TypeError)):
        cfg.host = "outro"  # type: ignore[misc]


def test_configuracao_existe_como_tipo_e_nao_como_tupla_solta():
    """Guarda de assinatura: os dois consumidores recebem o mesmo objeto."""
    assert isinstance(le_configuracao(_ambiente_completo()), Configuracao)
