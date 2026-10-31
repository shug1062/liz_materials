import ctypes
import socket
import subprocess
import sys
import time
import webbrowser

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
PORT = 8000


def open_browser_when_ready(server: subprocess.Popen) -> None:
    for _ in range(60):
        if server.poll() is not None:
            return
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", PORT)) == 0:
                webbrowser.open(f"http://localhost:{PORT}/")
                return
        time.sleep(0.5)


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("This launcher is only for Windows.")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_execution_state = kernel32.SetThreadExecutionState
    set_execution_state.argtypes = [ctypes.c_uint]
    set_execution_state.restype = ctypes.c_uint

    if not set_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED):
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        server = subprocess.Popen([
            sys.executable, "-m", "waitress", f"--listen=0.0.0.0:{PORT}", "--threads=8",
            "studio.wsgi:application",
        ])
        open_browser_when_ready(server)
        return server.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if not set_execution_state(ES_CONTINUOUS):
            raise ctypes.WinError(ctypes.get_last_error())


if __name__ == "__main__":
    raise SystemExit(main())
