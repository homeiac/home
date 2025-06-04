from pathlib import Path
import sys

# Ensure the package under ../src is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
