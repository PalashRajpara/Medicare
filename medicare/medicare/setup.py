"""Backwards compatibility shim for medicare.medicare.setup."""

from medicare.medicare.dataset.cli import *  # noqa: F403
from medicare.medicare.dataset.cli import main

if __name__ == "__main__":
    main()
