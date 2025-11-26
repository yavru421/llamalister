import sys
import traceback


PRINT_PREFIX = "[APT] Fatal Mode Active:"


def strict_excepthook(exc_type, exc_value, exc_tb):
    """Print the fatal error message, the traceback, and exit."""
    type_name = getattr(exc_type, "name", exc_type.__name__)
    print(f"\n[FATAL ERROR] APT FATAL ERROR: {type_name} - {exc_value}")
    traceback.print_tb(exc_tb)
    sys.exit(1)


sys.excepthook = strict_excepthook
print(f"{PRINT_PREFIX} All exceptions are terminal.")
