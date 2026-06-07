#!/usr/bin/env python3
"""<NAME> agent — entry point."""
from __future__ import annotations

import os
import sys


def main(argv: list[str]) -> int:
    serverchan = os.environ.get("SERVERCHAN_KEY")
    if not serverchan:
        print("SERVERCHAN_KEY missing in .env", file=sys.stderr)
        return 1

    # TODO: implement <NAME> agent logic
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
