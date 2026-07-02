from pathlib import Path
import pytest


class TestAppConfig:
    def test_default_construction(self):
        from core.models import AppConfig

        cfg = AppConfig(name="test_app", path=Path("/exe"), enable=True, level=1, ics=False)
        assert cfg.name == "test_app"
        assert cfg.enable is True
        assert cfg.level == 1
        assert cfg.ics is False
        assert cfg.depends_on == []

    def test_path_coercion_from_string(self):
        from core.models import AppConfig

        cfg = AppConfig(name="test", path="C:/some/path", enable=True, level=0, ics=False)
        assert isinstance(cfg.path, Path)
        assert str(cfg.path) == "C:\\some\\path" or str(cfg.path) == "C:/some/path"

    def test_depends_on_list(self):
        from core.models import AppConfig

        cfg = AppConfig(name="test", path=Path("/exe"), enable=True, level=1, ics=False, depends_on=["other"])
        assert cfg.depends_on == ["other"]

    def test_empty_name_raises_value_error(self):
        from core.models import AppConfig
        from pathlib import Path

        with pytest.raises(ValueError, match="non-empty"):
            AppConfig(name="", path=Path("/exe"), enable=True, level=1, ics=False)

    def test_whitespace_name_raises_value_error(self):
        from core.models import AppConfig
        from pathlib import Path

        with pytest.raises(ValueError, match="non-empty"):
            AppConfig(name="   ", path=Path("/exe"), enable=True, level=1, ics=False)

    def test_enable_non_bool_raises_type_error(self):
        from core.models import AppConfig
        from pathlib import Path

        with pytest.raises(TypeError):
            AppConfig(name="test", path=Path("/exe"), enable=1, level=1, ics=False)

    def test_ics_non_bool_raises_type_error(self):
        from core.models import AppConfig
        from pathlib import Path

        with pytest.raises(TypeError):
            AppConfig(name="test", path=Path("/exe"), enable=True, level=1, ics=1)

    def test_negative_level_raises_value_error(self):
        from core.models import AppConfig
        from pathlib import Path

        with pytest.raises(ValueError, match="non-negative"):
            AppConfig(name="test", path=Path("/exe"), enable=True, level=-1, ics=False)

    def test_level_non_int_raises_value_error(self):
        from core.models import AppConfig
        from pathlib import Path

        with pytest.raises(ValueError, match="non-negative"):
            AppConfig(name="test", path=Path("/exe"), enable=True, level="1", ics=False)

    def test_to_dict(self):
        from core.models import AppConfig

        cfg = AppConfig(name="test", path=Path("/exe"), enable=True, level=2, ics=True, depends_on=["a"])
        d = cfg.to_dict()
        assert d["name"] == "test"
        assert d["enable"] is True
        assert d["level"] == 2
        assert d["ics"] is True
        assert d["depends_on"] == ["a"]

    def test_from_dict(self):
        from core.models import AppConfig

        data = {
            "name": "from_dict",
            "path": "/some/path",
            "enable": False,
            "level": 3,
            "ics": True,
            "depends_on": ["other"],
        }
        cfg = AppConfig.from_dict(data)
        assert cfg.name == "from_dict"
        assert cfg.enable is False
        assert cfg.level == 3
        assert cfg.ics is True
        assert cfg.depends_on == ["other"]

    def test_roundtrip(self):
        from core.models import AppConfig
        from pathlib import Path

        original = AppConfig(name="roundtrip", path=Path("/bin"), enable=True, level=0, ics=False, depends_on=[])
        data = original.to_dict()
        restored = AppConfig.from_dict(data)
        assert restored.name == original.name
        assert restored.path == original.path
        assert restored.enable == original.enable
