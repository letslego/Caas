"""Enterprise Context-as-a-Service reference implementation."""

__version__ = "0.5.0"

from .factory import open_memory
from .multiscope import Conflict, Denied, Memory, Principal
from .sdk import CaasClient, CaasError

__all__ = [
    "CaasClient",
    "CaasError",
    "Conflict",
    "Denied",
    "Memory",
    "Principal",
    "open_memory",
    "__version__",
]
