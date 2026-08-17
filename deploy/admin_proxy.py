from __future__ import annotations

import asyncio
from functools import partial


async def relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()


async def proxy(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    host: str,
    port: int,
) -> None:
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(host, port)
        await asyncio.gather(
            relay(reader, upstream_writer),
            relay(upstream_reader, writer),
        )
    except (ConnectionError, OSError):
        writer.close()


async def main() -> None:
    servers = [
        await asyncio.start_server(partial(proxy, host=host, port=port), "0.0.0.0", port)
        for host, port in (("napcat", 6099), ("astrbot", 6185))
    ]
    await asyncio.gather(*(server.serve_forever() for server in servers))


if __name__ == "__main__":
    asyncio.run(main())
