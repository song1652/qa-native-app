"""Process-level helpers shared by environment management routes."""

import os
import socket
import subprocess
import time


def command_detail(result: subprocess.CompletedProcess) -> str:
    """Choose the most useful user-facing output from a failed command."""
    stderr = result.stderr.decode(errors="replace") if isinstance(result.stderr, bytes) else result.stderr
    stdout = result.stdout.decode(errors="replace") if isinstance(result.stdout, bytes) else result.stdout
    return (stderr or stdout or "명령 실행에 실패했습니다.").strip()


def wait_for_process_and_port_exit(
    pid: int,
    port: int,
    timeout: float = 5.0,
) -> bool:
    """Wait until both a process and its localhost listener are gone."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            process_alive = True
        except ProcessLookupError:
            process_alive = False
        except PermissionError:
            process_alive = True
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                port_open = True
        except OSError:
            port_open = False
        if not process_alive and not port_open:
            return True
        time.sleep(0.1)
    return False
