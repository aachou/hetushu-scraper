import io
import os
import sys

if sys.platform.startswith("win") and "PYTEST_VERSION" not in os.environ:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
