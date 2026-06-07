"""Phase 4 unit-test bootstrap.

This package is *normally* imported on its own:

    pytest tests/unit/

When mixed in the same collection with ``tests/packaging/`` (the Phase 2/3
build-script tests), pytest also adds ``tests/packaging/`` to ``sys.path``
and Python's namespace-package logic merges it with the PyPI ``packaging``
distribution — breaking ``from packaging.version import Version`` for
anyone downstream. See ``[[reference_test_env_importlib]]``.

For the mixed-run case, invoke each subtree separately:

    pytest tests/unit/
    pytest tests/packaging/ tests/scripts/

Both pass independently. CI batches them by group.
"""
