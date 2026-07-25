"""
auto_run.py — Background Autorunner Daemon Entry Point
Launches continuous keyword scraping daemon.
"""

import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from cli.auto_runner import run_autorunner

if __name__ == "__main__":
    run_autorunner()
