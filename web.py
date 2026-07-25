"""
web.py — Primary Web Console Entry Point
Launches the executive Flask web console application.
"""

import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from youtube_lead_generator.web.app import app

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
