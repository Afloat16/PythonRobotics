"""Read-only, dependency-free robot description checks."""
__version__ = "0.1.0"

from .core import check_file, check_text

__all__ = ["check_file", "check_text", "__version__"]
