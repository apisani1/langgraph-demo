"""Pytest configuration"""

import sys
from pathlib import Path


THIS_DIR = Path(__file__).parent
TESTS_DIR_PARENT = (THIS_DIR / "..").resolve()

# Ensure that `from tests ...` import statements work within the tests/ dir
sys.path.insert(0, str(TESTS_DIR_PARENT))

# Add src directory to path to ensure package can be importe
src_dir = TESTS_DIR_PARENT / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))
