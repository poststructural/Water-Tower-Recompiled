"""Entry point for the frozen launcher (PyInstaller) and for running from a
checkout: python launcher/run_launcher.py"""

import sys

from animaniacs_launcher.cli import main

if __name__ == "__main__":
    sys.exit(main())
