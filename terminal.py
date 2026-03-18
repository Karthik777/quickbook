"""Async PTY WebSocket handler for the inline terminal."""
import asyncio
import fcntl
import json
import os
import struct
import subprocess
import termios
from typing import Callable, Awaitable


class PtySession:
    """
    Persistent PTY bash session bridged to WebSocket.
    Uses pty.openpty() + subprocess + loop.add_reader() for event-driven I/O.
    One instance shared across all terminal WebSocket connections.
    """

    def __init__(self):
        self.master_fd: int | None = None
        self._proc: subprocess.Popen | None = None
        self._subscribers: set[Callable] = set()

    async def start(self):
        """Spawn bash with a PTY. Safe to call once."""
        import pty
        self.master_fd, slave_fd = pty.openpty()
        self._proc = subprocess.Popen(
            ["/bin/bash", "--login"],
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            close_fds=True,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        os.close(slave_fd)  # parent holds master end only

        # Non-blocking reads on master fd
        flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Register event-driven reader on the event loop
        loop = asyncio.get_event_loop()
        loop.add_reader(self.master_fd, self._on_readable)

    def _on_readable(self):
        """Called by the event loop when master_fd has data — no polling needed."""
        try:
            data = os.read(self.master_fd, 4096)
        except OSError:
            return
        if data and self._subscribers:
            for send_fn in list(self._subscribers):
                asyncio.ensure_future(send_fn(data.decode(errors="replace")))

    async def write(self, data: str | bytes):
        if self.master_fd is None:
            return
        if isinstance(data, str):
            data = data.encode()
        await asyncio.to_thread(os.write, self.master_fd, data)

    def resize(self, rows: int, cols: int):
        if self.master_fd is None:
            return
        size = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size)

    def subscribe(self, send_fn: Callable):
        self._subscribers.add(send_fn)

    def unsubscribe(self, send_fn: Callable):
        self._subscribers.discard(send_fn)

    def close(self):
        if self.master_fd is not None:
            try:
                loop = asyncio.get_event_loop()
                loop.remove_reader(self.master_fd)
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        if self._proc:
            self._proc.terminate()
            self._proc = None


# App-level singleton (created on first terminal connection)
_session: PtySession | None = None


async def get_pty() -> PtySession:
    global _session
    if _session is None:
        _session = PtySession()
        await _session.start()
    return _session
