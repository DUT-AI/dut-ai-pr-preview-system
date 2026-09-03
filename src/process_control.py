"""Cross-platform subprocess-group cleanup for review runtimes."""
from __future__ import annotations

import os
import signal
import subprocess


PROCESS_STOP_SECONDS = 5


def _is_windows() -> bool:
    return os.name == "nt"


def process_group_options() -> dict:
    """Popen options that isolate a child and all descendants as one group."""
    if _is_windows():
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _windows_process_alive(pid: int) -> bool:
    """Probe a PID without signalling or terminating it on Windows."""
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    error_invalid_parameter = 87

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        # A nonexistent PID reports ERROR_INVALID_PARAMETER. Any other error is
        # inconclusive, so treat it as alive rather than stealing a live lock.
        return ctypes.get_last_error() != error_invalid_parameter
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            # An inconclusive probe must not make callers steal a live lock.
            return True
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def process_is_alive(pid: int) -> bool:
    """Return whether ``pid`` exists without changing the target process."""
    if pid <= 0:
        return False
    if _is_windows():
        return _windows_process_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_process_tree(process, timeout: float = PROCESS_STOP_SECONDS) -> None:
    """Stop a Popen child and every runtime process it spawned."""
    if process.poll() is not None:
        return
    try:
        if _is_windows():
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ValueError):
        try:
            process.terminate()
        except OSError:
            return
    try:
        process.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass

    if _is_windows():
        # terminate() reaches only the Python child. /T also reaches its exact
        # descendants; argv avoids shell parsing of the validated integer PID.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
