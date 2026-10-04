import pytest
import sys
from pathlib import Path

# Ensure src directory is in sys.path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))
