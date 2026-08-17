from __future__ import annotations

import asyncio
import ctypes
import json
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import uuid4

UpdateHandler = Callable[[dict[str, Any]], Awaitable[None]]


class TDJson:
    def __init__(self, library_path: str) -> None:
        path = Path(library_path)
        if not path.exists():
            raise FileNotFoundError(f"TDLib JSON library not found: {path}")
        self.library = ctypes.CDLL(str(path))
        self.library.td_set_log_verbosity_level.argtypes = [ctypes.c_int]
        self.library.td_create_client_id.restype = ctypes.c_int
        self.library.td_send.argtypes = [ctypes.c_int, ctypes.c_char_p]
        self.library.td_receive.argtypes = [ctypes.c_double]
        self.library.td_receive.restype = ctypes.c_char_p
        # TDLib 的调试输出可能包含认证请求参数，生产环境必须完全关闭。
        self.library.td_set_log_verbosity_level(0)
        self.client_id = int(self.library.td_create_client_id())
        self.pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.receive_task: asyncio.Task[None] | None = None
        self.update_tasks: set[asyncio.Task[None]] = set()
        # TDLib 要求 td_receive 始终由同一个线程调用，不能使用共享线程池。
        self.receive_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="tdlib-receive"
        )

    def send(self, payload: dict[str, Any]) -> None:
        self.library.td_send(
            self.client_id,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
        )

    async def request(self, payload: dict[str, Any], timeout_seconds: float = 30) -> dict[str, Any]:
        extra = uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.pending[extra] = future
        self.send({**payload, "@extra": extra})
        try:
            return await asyncio.wait_for(future, timeout_seconds)
        finally:
            self.pending.pop(extra, None)

    def start(self, handler: UpdateHandler) -> None:
        self.receive_task = asyncio.create_task(self._receive(handler), name="tdlib-receive")

    async def close(self) -> None:
        if self.receive_task:
            self.receive_task.cancel()
            await asyncio.gather(self.receive_task, return_exceptions=True)
        for task in self.update_tasks:
            task.cancel()
        await asyncio.gather(*self.update_tasks, return_exceptions=True)
        self.receive_executor.shutdown(wait=True, cancel_futures=True)
        self.send({"@type": "close"})

    def _receive_once(self) -> dict[str, Any] | None:
        raw = self.library.td_receive(1.0)
        return json.loads(raw.decode()) if raw else None

    async def _receive(self, handler: UpdateHandler) -> None:
        while True:
            payload = await asyncio.get_running_loop().run_in_executor(
                self.receive_executor, self._receive_once
            )
            if not payload:
                continue
            extra = payload.get("@extra")
            future = self.pending.get(str(extra)) if extra else None
            if future and not future.done():
                future.set_result(payload)
            else:
                task = asyncio.create_task(
                    self._handle_update(handler, payload), name="tdlib-update-handler"
                )
                self.update_tasks.add(task)
                task.add_done_callback(self._finish_update_task)

    async def _handle_update(self, handler: UpdateHandler, payload: dict[str, Any]) -> None:
        await handler(payload)

    def _finish_update_task(self, task: asyncio.Task[None]) -> None:
        self.update_tasks.discard(task)
        if not task.cancelled():
            task.exception()
