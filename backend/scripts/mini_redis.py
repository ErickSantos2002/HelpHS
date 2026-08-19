"""
Mini-servidor compatível com o subconjunto de Redis que o HelpHS usa em dev
local (tokens de auth: SETEX/GET/DEL/EXISTS). Não é Redis de verdade — é só
para rodar o app localmente sem Docker. RESP2, sem persistência.
"""

import asyncio
import time

STORE: dict[str, tuple[str, float | None]] = {}  # key -> (value, expira_em)


def _get(key: str):
    item = STORE.get(key)
    if item is None:
        return None
    value, exp = item
    if exp is not None and time.monotonic() > exp:
        STORE.pop(key, None)
        return None
    return value


async def _read_command(reader: asyncio.StreamReader):
    line = await reader.readline()
    if not line:
        return None
    line = line.strip()
    if not line.startswith(b"*"):
        # comando inline (raro) — ignora
        return [p.decode() for p in line.split()]
    n = int(line[1:])
    parts = []
    for _ in range(n):
        header = await reader.readline()  # $len
        length = int(header.strip()[1:])
        data = await reader.readexactly(length + 2)  # payload + \r\n
        parts.append(data[:-2].decode())
    return parts


async def handle(reader, writer):
    try:
        while True:
            cmd = await _read_command(reader)
            if cmd is None:
                break
            name = cmd[0].upper() if cmd else ""
            if name == "PING":
                out = b"+PONG\r\n"
            elif name == "SETEX" and len(cmd) >= 4:
                STORE[cmd[1]] = (cmd[3], time.monotonic() + float(cmd[2]))
                out = b"+OK\r\n"
            elif name == "SET" and len(cmd) >= 3:
                exp = None
                if len(cmd) >= 5 and cmd[3].upper() in ("EX", "PX"):
                    ttl = float(cmd[4]) / (1000 if cmd[3].upper() == "PX" else 1)
                    exp = time.monotonic() + ttl
                STORE[cmd[1]] = (cmd[2], exp)
                out = b"+OK\r\n"
            elif name == "GET" and len(cmd) >= 2:
                v = _get(cmd[1])
                out = (
                    b"$-1\r\n"
                    if v is None
                    else f"${len(v.encode())}\r\n{v}\r\n".encode()
                )
            elif name in ("DEL", "UNLINK"):
                n = sum(1 for k in cmd[1:] if STORE.pop(k, None) is not None)
                out = f":{n}\r\n".encode()
            elif name == "EXISTS":
                n = sum(1 for k in cmd[1:] if _get(k) is not None)
                out = f":{n}\r\n".encode()
            elif name in ("EXPIRE", "PEXPIRE"):
                v = _get(cmd[1])
                if v is None:
                    out = b":0\r\n"
                else:
                    ttl = float(cmd[2]) / (1000 if name == "PEXPIRE" else 1)
                    STORE[cmd[1]] = (v, time.monotonic() + ttl)
                    out = b":1\r\n"
            elif name == "TTL":
                item = STORE.get(cmd[1])
                if item is None:
                    out = b":-2\r\n"
                else:
                    _, exp = item
                    out = f":{int(exp - time.monotonic()) if exp else -1}\r\n".encode()
            else:
                # AUTH, SELECT, CLIENT SETINFO, INFO etc.: aceita e segue
                out = b"+OK\r\n"
            writer.write(out)
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionResetError):
        pass
    finally:
        writer.close()


async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", 6379)
    print("mini-redis ouvindo em 127.0.0.1:6379", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
