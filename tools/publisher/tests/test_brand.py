import subprocess
import pytest
from locksmith_publisher import brand


class _R:
    def __init__(self, rc, out, err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_release_prefix_from_brandlib(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(0, "usurance/releases\n"))
    assert brand.release_prefix() == "usurance/releases"


def test_artifact_prefix_from_brandlib(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(0, "Usurance\n"))
    assert brand.artifact_prefix() == "Usurance"


def test_website_from_brandlib(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(0, "https://usurance.com\n"))
    assert brand.website() == "https://usurance.com"


def test_fail_loud_on_nonzero(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(1, "", "boom"))
    with pytest.raises(RuntimeError):
        brand.release_prefix()


def test_fail_loud_on_empty(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(0, "  \n"))
    with pytest.raises(RuntimeError):
        brand.artifact_prefix()
