"""Enterprise Context-as-a-Service reference implementation."""

__version__ = "0.4.0"

from .factory import open_memory
from .multiscope import Conflict, Denied, Memory, Principal

__all__ = [
    "Conflict",
    "Denied",
    "Memory",
    "Principal",
    "open_memory",
    "__version__",
]
