"""Tests for ``tools/gen_reference.py`` (code-derived reference docs).

The generator is a script, not part of a package, so it is loaded with
``importlib`` from the repo root — same approach as ``build.py`` in
``test_release_assembly.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_generator() -> ModuleType:
    """Import ``tools/gen_reference.py`` as a standalone module."""
    spec = importlib.util.spec_from_file_location(
        "gen_reference", REPO_ROOT / "tools" / "gen_reference.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_reference"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _load_generator()


class TestErrorCodes:
    def test_every_registered_code_is_rendered(self, generator: ModuleType) -> None:
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from core.error_codes import list_all_codes

        codes = list_all_codes()
        text = generator.render_error_codes()

        assert len(codes) > 100
        for code in codes:
            assert f"### `{code.code}`" in text
        assert text.count("\n### `") == len(codes)

    def test_generated_notice_present(self, generator: ModuleType) -> None:
        assert generator.GENERATED_NOTE in generator.render_error_codes()


class TestConfigReference:
    def test_sections_and_new_keys(self, generator: ModuleType) -> None:
        text = generator.render_config()

        for section in ("gifts", "tiktok", "update", "builtins"):
            assert f"## `{section}`" in text
        assert "`auto_sync`" in text
        assert "`source`" in text
        assert "`diamond_value_usd`" in text
        assert "`auto_update_config`" in text

    def test_nested_keys_are_indented_bullets(self, generator: ModuleType) -> None:
        text = generator.render_config()

        assert "  - **`mode`**" in text

    def test_missing_file_raises(self, generator: ModuleType, tmp_path: Path) -> None:
        with pytest.raises(OSError):
            generator.render_config(tmp_path / "nope.yaml")


class TestApiReference:
    def test_gift_endpoints_are_listed(self, generator: ModuleType) -> None:
        text = generator.render_api()

        assert "| POST | `/api/v1/gifts/sync` |" in text
        assert "| GET | `/api/v1/gifts` |" in text
        assert "/api/v1/diagnostics/error-codes" in text

    def test_overview_table_present(self, generator: ModuleType) -> None:
        text = generator.render_api()

        assert "| Tag | Endpoints |" in text
        assert text.count("\n## ") >= 2


class TestWriteAndCheck:
    def test_write_creates_all_pages(
        self, generator: ModuleType, tmp_path: Path
    ) -> None:
        written = generator.write_reference(tmp_path)

        assert {path.name for path in written} == {
            "error-codes.md",
            "config.md",
            "api.md",
        }
        assert all(path.is_file() for path in written)
        assert generator.check_reference(tmp_path) == []

    def test_check_detects_stale_and_missing(
        self, generator: ModuleType, tmp_path: Path
    ) -> None:
        generator.write_reference(tmp_path)
        config_page = tmp_path / "config.md"
        config_page.write_text("mutated", encoding="utf-8")
        (tmp_path / "api.md").unlink()

        stale = generator.check_reference(tmp_path)

        assert config_page in stale
        assert tmp_path / "api.md" in stale
        assert tmp_path / "error-codes.md" not in stale


class TestCellEscaping:
    def test_pipes_and_whitespace(self, generator: ModuleType) -> None:
        assert generator._cell("a | b\n  c") == "a \\| b c"

    def test_empty_value(self, generator: ModuleType) -> None:
        assert generator._cell(None) == "—"
