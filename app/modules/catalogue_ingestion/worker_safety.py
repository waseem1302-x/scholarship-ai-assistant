"""Runtime-observed operator stop controls for catalogue work."""

from __future__ import annotations

from pathlib import Path


class WorkerKillSwitchActive(RuntimeError):
    """Raised when paid catalogue work must pause immediately."""


def kill_switch_active(path: str | None) -> bool:
    """Fail closed when a configured switch is active or cannot be observed."""

    if not path:
        return False
    try:
        switch = Path(path)
        return switch.is_file() or not switch.parent.is_dir()
    except OSError:
        return True


def kill_switch_available(path: str | None) -> bool:
    """Return whether an operator can create/remove the configured switch file."""

    if not path:
        return False
    try:
        switch = Path(path)
        return switch.parent.is_dir() and not switch.is_dir()
    except OSError:
        return False
