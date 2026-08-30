import os
import sys

if sys.platform.startswith("win") and "PYTEST_VERSION" not in os.environ:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
