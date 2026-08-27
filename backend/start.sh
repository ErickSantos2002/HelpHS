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
# O BACKPLANE JA EXISTE (app/services/chat_backplane.py, Redis pub/sub): cada
# worker assina um canal e reemite para os proprios sockets, com carimbo de
# origem para nao entregar duas vezes. Ou seja, o impedimento tecnico acabou.
#
# O numero segue em 1 por ESTAGIO, nao por falta: com um worker so, o assinante
# ja sobe, publica, recebe as proprias mensagens e as descarta pelo carimbo --
# fica exercitado em producao sem risco nenhum. O readiness reporta
# `chat_backplane.assinado`; depois de alguns dias mostrando a assinatura de pe,
# subir para dois vira trocar este numero, com evidencia atras.
#
# Uma coisa que o backplane NAO resolve: pub/sub nao guarda nada. Durante uma
# reassinatura, o que os outros publicarem para este worker se perde -- a
# mensagem fica no banco e aparece no F5, mas ninguem sabe que precisa dar F5.
#
# O lock no Redis do fechamento automatico (app/services/ticket_lifecycle.py)
# FICA, mesmo sendo desnecessario com um worker so: voltar a dois e mudar um
# numero nesta linha, e sem o lock essa volta duplicaria histórico e
# notificacao de cada chamado fechado -- calada, como a do chat.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
