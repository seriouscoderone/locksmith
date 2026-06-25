"""sparkle_init loads the bundled Sparkle.framework via objc.loadBundle.

The long-standing bug was `from Sparkle import SPUStandardUpdaterController` —
a binding that cannot exist (Sparkle is third-party; there is no
pyobjc-framework-Sparkle). That import always raised ModuleNotFoundError, so
the macOS updater never initialized. These tests cover the framework-path
resolver and guard against the broken import regressing. The live framework
load (objc.loadBundle + initWithStartingUpdater…) is validated against a real
bundled Sparkle.framework on macOS, not here.
"""
import importlib.util

si = importlib.import_module("locksmith.update.sparkle_init")


def test_no_broken_sparkle_import_statement():
    """No actual `from Sparkle import …` statement (it never resolved). Checks
    the AST, not text, so the explanatory comments don't trip it."""
    import ast

    origin = importlib.util.find_spec("locksmith.update.sparkle_init").origin
    tree = ast.parse(open(origin, encoding="utf-8").read())
    sparkle_imports = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "Sparkle"
    ]
    assert sparkle_imports == []


def test_framework_path_frozen_resolves_contents_frameworks(monkeypatch, tmp_path):
    contents = tmp_path / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    fw = contents / "Frameworks" / "Sparkle.framework"
    fw.mkdir(parents=True)
    exe = contents / "MacOS" / "Locksmith"
    exe.write_text("")
    monkeypatch.setattr(si.sys, "frozen", True, raising=False)
    monkeypatch.setattr(si.sys, "executable", str(exe))
    assert si._sparkle_framework_path() == fw


def test_framework_path_frozen_absent_falls_back_or_none(monkeypatch, tmp_path):
    exe = tmp_path / "Contents" / "MacOS" / "Locksmith"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(si.sys, "frozen", True, raising=False)
    monkeypatch.setattr(si.sys, "executable", str(exe))
    res = si._sparkle_framework_path()
    # No framework next to the (fake) frozen exe → repo fallback or None.
    assert res is None or res.name == "Sparkle.framework"
