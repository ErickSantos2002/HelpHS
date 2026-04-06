"""
ClamAV antivirus scanner.

Uses the clamd INSTREAM protocol over TCP.

Protocol overview
-----------------
1. Connect to clamd on TCP host:port (default 3310).
2. Send the command ``zINSTREAM\\0`` (null-terminated).
3. Stream the file in chunks: each chunk is prefixed with a 4-byte big-endian
   length header.  A 4-byte zero terminates the stream.
4. Read the response:
   - ``stream: OK``            → file is clean
   - ``stream: <name> FOUND``  → virus detected
   - Any other response        → treat as scan error

If ClamAV is unreachable (ConnectionRefusedError / timeout) the function
returns ``(False, "unavailable")`` and the caller decides whether to block
or allow the upload.
"""

import asyncio
import struct

from loguru import logger

_CHUNK_SIZE = 2048


async def scan_bytes(
    data: bytes,
    host: str,
    port: int,
    timeout: int = 30,
) -> tuple[bool, str]:
    """
    Scan `data` with ClamAV via the INSTREAM protocol.

    Returns
    -------
    (True,  "clean")              — file is safe
    (False, "Virus: <name>")      — virus detected
    (False, "unavailable")        — ClamAV unreachable / timed out
    (False, "error: <msg>")       — unexpected response
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
    except (TimeoutError, ConnectionRefusedError, OSError) as exc:
        logger.warning(f"ClamAV unreachable at {host}:{port} — {exc}")
        return False, "unavailable"

    try:
        writer.write(b"zINSTREAM\0")

        for i in range(0, len(data), _CHUNK_SIZE):
            chunk = data[i : i + _CHUNK_SIZE]
            writer.write(struct.pack(">I", len(chunk)) + chunk)

        writer.write(b"\0\0\0\0")  # end-of-stream
        await writer.drain()

        raw = await asyncio.wait_for(reader.read(256), timeout=timeout)
        response = raw.decode(errors="replace").strip()

        if response.endswith("OK"):
            return True, "clean"

        if "FOUND" in response:
            virus_name = response.replace("stream:", "").replace("FOUND", "").strip()
            logger.warning(f"ClamAV detected virus: {virus_name}")
            return False, f"Virus: {virus_name}"

        logger.error(f"ClamAV unexpected response: {response!r}")
        return False, f"error: {response}"

    except TimeoutError:
        logger.warning("ClamAV scan timed out")
        return False, "unavailable"
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
