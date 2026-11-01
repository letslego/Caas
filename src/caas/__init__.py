"""Enterprise Context-as-a-Service reference implementation."""

__version__ = "0.6.0"

from .context_service import ContextService, open_context
from .factory import open_memory
from .multiscope import Conflict, Denied, Memory, Principal
from .sdk import CaasClient, CaasError

__all__ = [
    "CaasClient",
    "CaasError",
    "Conflict",
    "ContextService",
    "Denied",
    "Memory",
    "Principal",
    "open_context",
    "open_memory",
    "__version__",
]
