"""
O fuso da agenda: a janela do mês e as bordas do evento de dia inteiro.

Até aqui a agenda não tinha hora. A tela mandava `T00:00:00Z` e `T23:59:59Z` a
partir de dois campos de data, e a janela do mês era calculada em UTC — nada
disso aparecia como defeito porque todo evento ocupava o dia inteiro, e um dia
inteiro sobrevive a qualquer deslocamento de três horas.

Com hora de verdade, os dois viram defeito no mesmo dia.

A JANELA SEGUE QUEM OLHA
------------------------
Um evento às 22:00 do dia 31 de janeiro, em Recife, é `01:00Z` do dia 1º de
fevereiro. Com a janela em UTC, janeiro terminava às `00:00Z` do dia 1º e o
evento ficava de fora: a pessoa criava em janeiro e ele aparecia em fevereiro.

Então a janela é construída no fuso de quem consulta e convertida para UTC na
saída, porque é `timestamptz` que está do outro lado.

DIA INTEIRO É DATA FLUTUANTE
----------------------------
E aqui está a decisão que não é óbvia: o evento de dia inteiro **não** é
ancorado no fuso de quem olha. Ele vale das `00:00:00Z` às `23:59:59.999999Z`
da data escolhida, e a tela o desenha pela DATA, não pelo instante. É o modelo
do `VALUE=DATE` do iCalendar.

A razão é concreta. Todo evento que já existe foi gravado como
`00:00:00Z`–`23:59:59Z`. Se dia inteiro passasse a ser ancorado em Recife, cada
um deles começaria às 21:00 do dia ANTERIOR — a agenda inteira andaria um dia
para trás sem ninguém ter editado coisa nenhuma, e consertar isso exigiria
reescrever as linhas antigas. Ancorado em UTC, a data guardada continua sendo a
data que a pessoa escolheu, e o recálculo não precisa existir.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Quem opera o sistema está em Recife. O padrão não é UTC de propósito: cair em
# UTC por omissão seria escolher o fuso de ninguém, e um cliente antigo que não
# mande o parâmetro veria o mês deslocado três horas sem nenhum aviso.
#
# Pernambuco nunca entrou no horário de verão — nem antes de ele acabar no país
# em 2019, porque o decreto alcançava Sul, Sudeste e Centro-Oeste. Por isso o
# deslocamento é fixo o ano inteiro, e há teste cobrando essa premissa: se ela
# mudar, a aritmética da janela precisa mudar junto.
FUSO_PADRAO = ZoneInfo("America/Recife")

# A âncora do evento de dia inteiro. Ele NÃO usa o fuso de quem olha — ver a
# seção acima —, e por isso a consulta do mês precisa de duas janelas: a local,
# para os eventos com hora, e esta, para os de dia inteiro.
#
# Sem as duas, um evento de dia inteiro do dia 1º (00:00Z–23:59:59Z) cai também
# no mês ANTERIOR: a janela local começa às 03:00Z do dia 1º, e o instante em
# que ele começa é anterior a isso. Em Recife ele "começa" às 21:00 do dia 31.
# Para um evento com hora isso é a verdade; para um de dia inteiro é o
# deslocamento que a ancoragem em UTC existe para negar.
FUSO_UTC = ZoneInfo("UTC")


def resolve_fuso(nome: str | None) -> ZoneInfo:
    """O fuso pedido, ou o padrão. Nome desconhecido é recusado, não ignorado.

    Voltar calado para o padrão faria um cliente com o fuso escrito errado
    receber o mês de outro lugar e nunca descobrir: o sintoma seria "alguns
    eventos somem", meses depois, sem nada apontando para a letra trocada.
    """
    if nome is None:
        return FUSO_PADRAO
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Fuso horário desconhecido: {nome!r}.") from exc


def janela_do_mes(ano: int, mes: int, fuso: ZoneInfo) -> tuple[datetime, datetime]:
    """O mês civil no fuso pedido, em UTC: `[início, fim)`.

    O fim é o primeiro instante do mês seguinte, e não o último do mês — meia
    noite exata do dia 1º pertence ao mês novo, e um intervalo fechado nos dois
    lados poria um evento que começa nesse instante em dois meses ao mesmo
    tempo.
    """
    inicio = datetime(ano, mes, 1, tzinfo=fuso)
    if mes == 12:
        fim = datetime(ano + 1, 1, 1, tzinfo=fuso)
    else:
        fim = datetime(ano, mes + 1, 1, tzinfo=fuso)
    return inicio.astimezone(UTC), fim.astimezone(UTC)


def bordas_do_dia_inteiro(inicio: datetime, fim: datetime) -> tuple[datetime, datetime]:
    """As bordas em UTC da data de início e da data de fim.

    A hora que veio junto é DESCARTADA. Sem isso, marcar "dia inteiro" num
    evento que já tinha 14:30 guardaria 14:30 e a chave diria outra coisa — o
    registro passaria a se contradizer, e quem lesse a coluna sem ler a chave
    veria um evento de meia tarde.

    O fim é o último microssegundo do dia, e não o primeiro do dia seguinte:
    assim a coluna continua dizendo, sozinha, em que dia o evento termina. Um
    fim em `00:00` do dia seguinte faria toda leitura que não conhece a
    convenção mostrar um dia a mais.
    """
    primeiro = inicio.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    ultimo = fim.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return primeiro, ultimo + timedelta(days=1) - timedelta(microseconds=1)
