"""Healthcheck for the dashboard API service."""

from __future__ import annotations

import sys
from urllib.error import URLError
from urllib.request import urlopen


def main() -> int:
    """Check the local dashboard health endpoint."""
    try:
        with urlopen("http://127.0.0.1:8000/health", timeout=5) as response:
            return 0 if response.status == 200 else 1
    except URLError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
