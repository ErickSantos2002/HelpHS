#!/bin/bash
set -e

echo "Running Alembic migrations..."
alembic upgrade head
echo "Migrations complete."

echo "Running database seeds..."
python -m app.seeds
echo "Seeds complete."

# UM worker, de proposito.
#
# O chat em tempo real guarda as conexoes WebSocket na memoria DO PROCESSO
# (ConnectionManager, em app/routers/chat.py: um dicionario de salas por
# ticket). Com dois workers, duas pessoas no mesmo chamado caem em processos
# diferentes com probabilidade alta, cada uma numa "sala" que o outro processo
# nao enxerga: as duas ficam conectadas, sem erro nenhum, e simplesmente nao
# recebem a mensagem uma da outra. Falha silenciosa, dificil de reproduzir e
# facil de confundir com problema de rede do usuario.
#
# Para voltar a dois (ou mais) e preciso ANTES existir um backplane -- um
# canal por fora do processo, tipicamente Redis pub/sub, que reemita cada
# mensagem para os outros workers. Trocar o numero aqui sem isso reintroduz a
# falha silenciosa.
#
# O lock no Redis do fechamento automatico (app/services/ticket_lifecycle.py)
# FICA, mesmo sendo desnecessario com um worker so: voltar a dois e mudar um
# numero nesta linha, e sem o lock essa volta duplicaria histórico e
# notificacao de cada chamado fechado -- calada, como a do chat.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
