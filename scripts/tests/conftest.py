"""pytest plugin hooks for ``scripts/tests``.

These hooks (``pytest_addoption`` and ``pytest_collection_modifyitems``) MUST
live in a ``conftest.py`` — modern pytest no longer recognises them when
defined inside a regular test module, which silently breaks the ``--run-slow``
gate.
"""
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Also run slow tests (full run_all_tests.py suite).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="slow test — pass --run-slow to enable")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
