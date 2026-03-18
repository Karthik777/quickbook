"""Async PTY WebSocket handler for the inline terminal."""
import asyncio
import os
import pty
import fcntl
import termios
import struct
import signal
from typing import Callable


class PtyTerminal:
    def __init__(self):
        self.master_fd: int | None = None
        self.pid: int | None = None
        self._read_task: asyncio.Task | None = None

    def spawn(self, shell: str = "/bin/bash"):
        """Fork a PTY running shell. Call once per WebSocket connection."""
        self.pid, self.master_fd = pty.fork()
        if self.pid == 0:
            # Child process — replace with shell
            os.execvp(shell, [shell])
        # Parent: set non-blocking I/O on master fd
        flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def resize(self, rows: int, cols: int):
        """Notify PTY of terminal resize."""
        if self.master_fd is None:
            return
        size = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size)

    async def write(self, data: str | bytes):
        """Send keystrokes to PTY."""
        if self.master_fd is None:
            return
        if isinstance(data, str):
            data = data.encode()
        await asyncio.to_thread(os.write, self.master_fd, data)

    async def read_loop(self, send: Callable):
        """Continuously read PTY output and forward via WebSocket send callback."""
        loop = asyncio.get_event_loop()
        while self.master_fd is not None:
            try:
                data = await asyncio.to_thread(self._read_chunk)
                if data:
                    await send(data.decode(errors="replace"))
            except OSError:
                # PTY closed
                break
            await asyncio.sleep(0.01)

    def _read_chunk(self, size: int = 4096) -> bytes:
        try:
            return os.read(self.master_fd, size)
        except BlockingIOError:
            return b""
        except OSError:
            return b""

    def close(self):
        """Kill the child process and close the PTY."""
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGKILL)
                os.waitpid(self.pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
        self.master_fd = None
        self.pid = None


# One terminal per session (keyed by WebSocket id)
_terminals: dict[str, PtyTerminal] = {}


def get_terminal(session_id: str) -> PtyTerminal:
    if session_id not in _terminals:
        _terminals[session_id] = PtyTerminal()
    return _terminals[session_id]


def close_terminal(session_id: str):
    if session_id in _terminals:
        _terminals[session_id].close()
        del _terminals[session_id]
