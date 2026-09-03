from __future__ import annotations

import signal
import subprocess

import pytest

from src import process_control


def test_process_is_alive_uses_non_signalling_windows_probe(monkeypatch):
    checked = []

    monkeypatch.setattr(process_control, "_is_windows", lambda: True)
    monkeypatch.setattr(
        process_control, "_windows_process_alive",
        lambda pid: checked.append(pid) or pid == 42,
    )
    monkeypatch.setattr(
        process_control.os, "kill",
        lambda *args: pytest.fail("os.kill must not probe Windows PIDs"),
    )

    assert process_control.process_is_alive(42) is True
    assert process_control.process_is_alive(43) is False
    assert checked == [42, 43]


def test_process_is_alive_classifies_posix_probe_errors(monkeypatch):
    monkeypatch.setattr(process_control, "_is_windows", lambda: False)

    monkeypatch.setattr(
        process_control.os, "kill",
        lambda pid, signal_number: (_ for _ in ()).throw(ProcessLookupError()),
    )
    assert process_control.process_is_alive(42) is False

    monkeypatch.setattr(
        process_control.os, "kill",
        lambda pid, signal_number: (_ for _ in ()).throw(PermissionError()),
    )
    assert process_control.process_is_alive(42) is True


def test_stop_process_tree_terminates_a_posix_process_group(monkeypatch):
    signals = []

    class Process:
        pid = 42

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(process_control, "_is_windows", lambda: False)
    monkeypatch.setattr(
        process_control.os, "killpg", lambda pid, value: signals.append((pid, value)),
        raising=False,
    )
    process_control.stop_process_tree(Process(), timeout=0.1)
    assert signals == [(42, signal.SIGTERM)]


def test_stop_process_tree_escalates_after_grace_period(monkeypatch):
    signals = []

    class Process:
        pid = 42

        def __init__(self):
            self.waits = 0

        def poll(self):
            return None

        def wait(self, timeout=None):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("engine", timeout)
            return -9

    monkeypatch.setattr(process_control, "_is_windows", lambda: False)
    monkeypatch.setattr(
        process_control.os, "killpg", lambda pid, value: signals.append((pid, value)),
        raising=False,
    )
    monkeypatch.setattr(process_control.signal, "SIGKILL", 9, raising=False)
    process_control.stop_process_tree(Process(), timeout=0.1)
    assert signals == [(42, signal.SIGTERM), (42, 9)]
