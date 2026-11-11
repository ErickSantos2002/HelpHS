"""
Mensagem do chat sem `seq` de propósito, nos testes (F1-B-04c).

A guarda `before_commit` de `app.services.chat_sequencia` avisa de toda
mensagem que vai para o commit sem número. Na suíte, o aviso REPROVA o teste
(fixture `_guarda_do_seq` do `conftest.py`): é assim que um escritor novo que
esquecer `numera_mensagens_do_chat` aparece vermelho, e não só num log.

Há quem grave sem número de propósito — o histórico anterior à migration, a
imagem antiga, o serviço testado sem o dono da transação. Duas formas de
declarar:

- `with sem_seq_intencional():` em volta só da gravação que simula o legado
  (é o que os helpers de semeadura fazem). O resto do teste segue vigiado.
- `@pytest.mark.mensagem_sem_seq` no teste inteiro, quando o teste É o caso
  (o próprio teste da guarda, por exemplo).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

intencional: ContextVar[bool] = ContextVar("mensagem_sem_seq_intencional", default=False)


@contextmanager
def sem_seq_intencional() -> Iterator[None]:
    marca = intencional.set(True)
    try:
        yield
    finally:
        intencional.reset(marca)
