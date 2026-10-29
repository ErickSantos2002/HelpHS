"""
A janela de tempo dos relatórios: de quando a quando, em que fuso, comparada
com o quê (F1-B-03a, 29/10/2026).

POR QUE EXISTE
--------------
Os relatórios só conheciam "N dias contados de agora para trás", em UTC. Na
tela isso virava "Ontem" = últimas 48 h e "Mês passado" = últimos 60 dias, e um
chamado aberto às 22:00 em Recife caía no dia seguinte do gráfico. Os
endpoints de técnico nem aceitavam datas, e exigiam `period >= 7` — o "Hoje"
da tela respondia 422.

O CONTRATO
----------
- `start_date` e `end_date` (AAAA-MM-DD) são DIAS DO CALENDÁRIO em
  `America/Recife`. O banco continua em UTC; a conversão acontece aqui.
- A janela é `[início, fim)`: 00:00 de `start_date` em Recife, incluída, até
  00:00 do dia seguinte a `end_date`, excluída. Meia-noite pertence ao dia que
  começa, e nenhum chamado conta em dois períodos vizinhos.
- As duas datas vêm juntas ou nenhuma; início não passa do fim; o fim não está
  no futuro; o intervalo tem no máximo 366 dias.
- Com datas, elas mandam: `period` é ignorado.
- Sem datas vale o `period` legado, com o MESMO significado de antes — N dias
  contados de agora para trás, sem limite superior —, para o front que já está
  no ar continuar recebendo os mesmos números.

A COMPARAÇÃO
------------
Um mês civil completo (dia 1º ao último dia) é comparado com o mês civil
anterior inteiro — "Mês passado" de outubro compara com setembro, não com os
31 dias antes de 1º de outubro. Qualquer outro intervalo é comparado com a
mesma quantidade de dias imediatamente antes. No `period` legado, a comparação
é a de sempre: os N dias anteriores ao início.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.utils.agenda import FUSO_PADRAO

# O mesmo fuso da agenda, e pelo mesmo motivo: é onde a equipe está. O SLA usa
# `America/Sao_Paulo`, que tem hoje o mesmo deslocamento; unificar os dois nomes
# é decisão registrada para outra frente.
FUSO_DOS_RELATORIOS: ZoneInfo = FUSO_PADRAO
NOME_DO_FUSO: str = FUSO_DOS_RELATORIOS.key

INTERVALO_MAXIMO_DIAS = 366


def deslocamento_do_fuso(fuso: ZoneInfo = FUSO_DOS_RELATORIOS) -> timedelta:
    """O deslocamento de Recife em relação a UTC: −3 h, o ano inteiro."""
    deslocamento = datetime(2026, 1, 1, tzinfo=fuso).utcoffset()
    assert deslocamento is not None
    return deslocamento


def intervalo_sql_do_fuso(deslocamento: timedelta | None = None) -> str:
    """O deslocamento como `INTERVAL` do Postgres — `INTERVAL '-03:00'`.

    O SQL agrupa por dia, dia da semana e hora com este intervalo, e NÃO com o
    nome do fuso. O nome exige a base de fusos instalada no Postgres, e o
    Postgres embutido do desenvolvimento local (pgserver no Windows) não tem
    nenhuma: `time zone "America/Recife" not recognized`. O intervalo vale em
    qualquer Postgres.

    Só é correto porque Recife não tem horário de verão (ver
    `agenda.FUSO_PADRAO`); há teste cobrando essa premissa. Se o fuso mudar
    para um com horário de verão, o agrupamento precisa voltar a usar o nome.
    """
    if deslocamento is None:
        deslocamento = deslocamento_do_fuso()
    minutos = int(deslocamento.total_seconds()) // 60
    sinal = "-" if minutos < 0 else "+"
    horas, resto = divmod(abs(minutos), 60)
    return f"INTERVAL '{sinal}{horas:02d}:{resto:02d}'"


@dataclass(frozen=True)
class JanelaDoRelatorio:
    """Uma janela já resolvida, com a comparação junto.

    `inicio` e `fim` são instantes UTC; `fim` é EXCLUSIVO e é `None` no
    `period` legado, que nunca teve limite superior. `primeiro_dia` e
    `ultimo_dia` são as datas locais que a janela cobre — as barras do gráfico
    diário são exatamente esses dias, nem um a mais.
    """

    inicio: datetime
    fim: datetime | None
    primeiro_dia: date
    ultimo_dia: date
    dias: int
    por_datas: bool
    anterior_inicio: datetime
    anterior_fim: datetime
    anterior_primeiro_dia: date
    anterior_ultimo_dia: date

    def dias_do_grafico(self) -> list[date]:
        """Cada dia local da janela, do primeiro ao último, inclusive."""
        total = (self.ultimo_dia - self.primeiro_dia).days + 1
        return [self.primeiro_dia + timedelta(days=i) for i in range(total)]


def meia_noite_local(dia: date) -> datetime:
    """00:00 de `dia` em Recife, como instante UTC."""
    return datetime.combine(dia, time.min, tzinfo=FUSO_DOS_RELATORIOS).astimezone(UTC)


def dia_local(instante: datetime) -> date:
    """A data em Recife de um instante com fuso."""
    return instante.astimezone(FUSO_DOS_RELATORIOS).date()


def _eh_mes_civil_completo(inicio: date, fim: date) -> bool:
    if inicio.day != 1 or (inicio.year, inicio.month) != (fim.year, fim.month):
        return False
    return (fim + timedelta(days=1)).day == 1


def _mes_anterior(primeiro_do_mes: date) -> tuple[date, date]:
    ultimo = primeiro_do_mes - timedelta(days=1)
    return ultimo.replace(day=1), ultimo


def resolve_janela(
    period: int,
    start_date: date | None,
    end_date: date | None,
    agora: datetime | None = None,
) -> JanelaDoRelatorio:
    """A janela pedida, ou `ValueError` com a mensagem que a pessoa vai ler.

    `agora` existe para os testes fixarem o relógio; em produção é o instante
    da chamada.
    """
    agora = agora or datetime.now(UTC)
    hoje = dia_local(agora)

    if (start_date is None) != (end_date is None):
        raise ValueError("Informe a data inicial e a data final, ou nenhuma das duas.")

    if start_date is not None and end_date is not None:
        if start_date > end_date:
            raise ValueError("A data inicial não pode ser posterior à data final.")
        if end_date > hoje:
            raise ValueError("A data final não pode estar no futuro.")
        dias = (end_date - start_date).days + 1
        if dias > INTERVALO_MAXIMO_DIAS:
            raise ValueError(f"O intervalo pode ter no máximo {INTERVALO_MAXIMO_DIAS} dias.")

        if _eh_mes_civil_completo(start_date, end_date):
            anterior_primeiro, anterior_ultimo = _mes_anterior(start_date)
        else:
            anterior_ultimo = start_date - timedelta(days=1)
            anterior_primeiro = start_date - timedelta(days=dias)

        return JanelaDoRelatorio(
            inicio=meia_noite_local(start_date),
            fim=meia_noite_local(end_date + timedelta(days=1)),
            primeiro_dia=start_date,
            ultimo_dia=end_date,
            dias=dias,
            por_datas=True,
            anterior_inicio=meia_noite_local(anterior_primeiro),
            anterior_fim=meia_noite_local(anterior_ultimo + timedelta(days=1)),
            anterior_primeiro_dia=anterior_primeiro,
            anterior_ultimo_dia=anterior_ultimo,
        )

    # `period` legado: o significado de sempre, de propósito.
    inicio = agora - timedelta(days=period)
    anterior_inicio = inicio - timedelta(days=period)
    return JanelaDoRelatorio(
        inicio=inicio,
        fim=None,
        primeiro_dia=dia_local(inicio),
        ultimo_dia=hoje,
        dias=period,
        por_datas=False,
        anterior_inicio=anterior_inicio,
        anterior_fim=inicio,
        anterior_primeiro_dia=dia_local(anterior_inicio),
        anterior_ultimo_dia=dia_local(inicio - timedelta(microseconds=1)),
    )
