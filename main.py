"""
main.py — Standalone Scraper CLI Entry Point
Launches interactive single-channel scraper pipeline.
"""

import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from cli.main import run_cli

if __name__ == "__main__":
    run_cli()
