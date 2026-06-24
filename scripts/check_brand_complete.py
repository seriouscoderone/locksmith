# -*- encoding: utf-8 -*-
"""Underscore alias so `import check_brand_complete` works (the executable
script is check-brand-complete.py; CI invokes the hyphenated form)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "_cbc_impl", Path(__file__).with_name("check-brand-complete.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
validate = _mod.validate
main = _mod.main
