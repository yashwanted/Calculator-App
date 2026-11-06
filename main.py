#!/usr/bin/env python3
"""Entry point: run with ``python3 main.py`` inside the virtual environment."""

import sys


def main() -> int:
    try:
        from calculator.ui import run
    except ImportError as error:
        print(
            f"Could not start Calculator: {error}\n\n"
            "Set up and activate the virtual environment first:\n"
            "  python3 -m venv .venv\n"
            "  source .venv/bin/activate\n"
            "  pip install -r requirements.txt\n",
            file=sys.stderr,
        )
        return 1
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from calculator.selftest import run_self_test

        return run_self_test(sys.argv[2])
    return run()


if __name__ == "__main__":
    sys.exit(main())
