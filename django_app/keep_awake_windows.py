import ctypes
import subprocess
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


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
        return subprocess.call([
            sys.executable, "-m", "waitress", "--listen=0.0.0.0:8000", "--threads=8",
            "studio.wsgi:application",
        ])
    except KeyboardInterrupt:
        return 0
    finally:
        if not set_execution_state(ES_CONTINUOUS):
            raise ctypes.WinError(ctypes.get_last_error())


if __name__ == "__main__":
    raise SystemExit(main())
