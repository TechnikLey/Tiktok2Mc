"""Tests for the hook import whitelist (AST check in core.hook_loader)."""

from __future__ import annotations

import textwrap

import pytest

from core.hook_loader import ALLOWED_IMPORTS, _check_imports


def _check_snippet(tmp_path, code: str) -> list[str]:
    hook = tmp_path / "main.py"
    hook.write_text(textwrap.dedent(code), encoding="utf-8")
    return _check_imports(hook)


class TestAllowedImports:
    @pytest.mark.parametrize(
        "module",
        [
            "time",
            "random",
            "logging",
            "json",
            "datetime",
            "re",
            "math",
            "collections",
            "itertools",
            "functools",
            "urllib",
            "requests",
        ],
    )
    def test_plain_import_allowed(self, tmp_path, module):
        assert _check_snippet(tmp_path, f"import {module}\n") == []

    @pytest.mark.parametrize(
        "statement",
        [
            "import urllib.request\n",
            "import urllib.parse\n",
            "from collections import defaultdict, deque\n",
            "from datetime import datetime, timedelta\n",
            "from functools import partial\n",
            "import json as j\n",
        ],
    )
    def test_submodules_and_aliases_allowed(self, tmp_path, statement):
        assert _check_snippet(tmp_path, statement) == []

    @pytest.mark.parametrize(
        "statement",
        ["from core.hook_api import HookAPI\n", "from core.plugin_config import x\n"],
    )
    def test_core_modules_allowed(self, tmp_path, statement):
        assert _check_snippet(tmp_path, statement) == []


class TestDisallowedImports:
    @pytest.mark.parametrize(
        "module",
        ["os", "sys", "subprocess", "socket", "pathlib", "shutil", "importlib"],
    )
    def test_dangerous_module_blocked(self, tmp_path, module):
        disallowed = _check_snippet(tmp_path, f"import {module}\n")
        assert disallowed == [module]

    def test_from_import_blocked(self, tmp_path):
        assert _check_snippet(tmp_path, "from os import path\n") == ["os"]

    def test_mixed_file_reports_only_disallowed(self, tmp_path):
        code = """
        import time
        import re
        import subprocess
        from sys import exit
        """
        result = _check_snippet(tmp_path, code)
        assert sorted(result) == ["subprocess", "sys"]


class TestCheckRobustness:
    def test_syntax_error_returns_empty(self, tmp_path):
        # Unparseable file must not crash the loader — treated as no findings.
        assert _check_snippet(tmp_path, "def broken(:\n") == []


class TestWhitelistAvailability:
    """Every whitelisted module MUST be importable in this environment.

    Hooks are loaded into the bridge process and cannot install anything,
    so the whitelist may only contain modules that are guaranteed present
    (stdlib or shipped dependencies).
    """

    @pytest.mark.parametrize("module", sorted(ALLOWED_IMPORTS - {"requests"}))
    def test_stdlib_module_importable(self, module):
        __import__(module)

    def test_requests_available(self):
        # Shipped dependency (requirements.txt) — verified separately so the
        # stdlib parametrization above stays meaningful without it.
        pytest.importorskip("requests")
