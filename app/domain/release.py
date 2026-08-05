"""Compile-time Release 1 execution safety boundary."""

from app.domain.enums import ExecutionMode

RELEASE_EXECUTION_CEILING = ExecutionMode.PAPER
ALLOWED_EXECUTION_MODES = frozenset({ExecutionMode.ALERT, ExecutionMode.PAPER})


def mode_is_available(mode: ExecutionMode) -> bool:
    """Return whether an execution mode exists in the current release."""
    return mode in ALLOWED_EXECUTION_MODES


def signing_is_available() -> bool:
    """Signing is deliberately unavailable in Release 1."""
    return False


def broadcasting_is_available() -> bool:
    """Broadcasting is deliberately unavailable in Release 1."""
    return False
