from pathlib import Path

import pytest


class TestLoadConfig:
    def test_load_valid_yaml(self, tmp_path):
        from core.utils import load_config

        f = tmp_path / "test.yaml"
        f.write_text("key: value\nnested: {a: 1}", encoding="utf-8")
        result = load_config(f)
        assert result == {"key": "value", "nested": {"a": 1}}

    def test_load_empty_file(self, tmp_path):
        from core.utils import load_config

        f = tmp_path / "empty.yaml"
        f.write_text("", encoding="utf-8")
        assert load_config(f) == {}

    def test_load_file_not_found(self):
        from core.utils import load_config

        with pytest.raises(FileNotFoundError):
            load_config(Path("/nonexistent/path.yaml"))

    def test_load_invalid_yaml(self, tmp_path):
        from core.utils import load_config

        f = tmp_path / "bad.yaml"
        f.write_text(": : invalid yaml ::", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML error"):
            load_config(f)
