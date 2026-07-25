import importlib, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "packaging"))
brandlib = importlib.import_module("brandlib")

def test_locksmith_is_flat_release():
    assert brandlib.brand_release_dir("locksmith", REPO) == REPO/"src"/"locksmith"/"release"

def test_other_brand_is_namespaced():
    assert brandlib.brand_release_dir("usurance", REPO) == REPO/"src"/"locksmith"/"release"/"usurance"
