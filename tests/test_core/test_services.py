import pytest
import yaml
from pathlib import Path


class TestNormalizeConfigVersion:
    def test_legacy_int(self):
        from core.utils import normalize_config_version
        assert normalize_config_version(7) == "0.7"
        assert normalize_config_version(0) == "0.0"
        assert normalize_config_version(10) == "0.10"

    def test_legacy_string_number(self):
        from core.utils import normalize_config_version
        assert normalize_config_version("7") == "0.7"
        assert normalize_config_version("0") == "0.0"

    def test_semantic_minor(self):
        from core.utils import normalize_config_version
        assert normalize_config_version("0.7") == "0.7"
        assert normalize_config_version("1.0") == "1.0"
        assert normalize_config_version("2.5") == "2.5"

    def test_v_prefix(self):
        from core.utils import normalize_config_version
        assert normalize_config_version("v1.0.0") == "1.0"
        assert normalize_config_version("v0.7.0") == "0.7"

    def test_triple_dot(self):
        from core.utils import normalize_config_version
        assert normalize_config_version("1.0.0") == "1.0"
        assert normalize_config_version("0.7.5") == "0.7"

    def test_whitespace_handling(self):
        from core.utils import normalize_config_version
        assert normalize_config_version("  1.0  ") == "1.0"
        assert normalize_config_version("  v2.0.0  ") == "2.0"

    def test_rejects_bad_strings(self):
        from core.utils import normalize_config_version
        with pytest.raises(ValueError):
            normalize_config_version("abc")
        with pytest.raises(ValueError):
            normalize_config_version("1.b")
        with pytest.raises(ValueError):
            normalize_config_version("v.")

    def test_rejects_bad_types(self):
        from core.utils import normalize_config_version
        with pytest.raises(ValueError):
            normalize_config_version([])
        with pytest.raises(ValueError):
            normalize_config_version(None)


@pytest.fixture
def svc(project_dir):
    from core.api.services import ApiService
    return ApiService()


class TestApiService:
    def test_read_config_returns_dict(self, svc):
        cfg = svc.read_config()
        assert isinstance(cfg, dict)
        assert cfg["config_version"] == "1.0"

    def test_read_config_normalises_version(self, svc, project_dir):
        config_file = project_dir / "config.yaml"
        original = config_file.read_text(encoding="utf-8")
        with config_file.open("w", encoding="utf-8") as f:
            yaml.dump({"config_version": 7}, f)

        try:
            cfg = svc.read_config()
            assert cfg["config_version"] == "0.7"
        finally:
            config_file.write_text(original, encoding="utf-8")

    def test_read_config_file_not_found(self, project_dir):
        from core.api.services import ApiService
        svc = ApiService()
        svc.config_path = project_dir / "nonexistent.yaml"
        with pytest.raises(FileNotFoundError):
            svc.read_config()

    def test_write_config_upgrades_version(self, svc):
        cfg = svc.read_config()
        cfg["config_version"] = "0.7"
        svc.write_config(cfg, backup=False)
        reread = svc.read_config()
        assert reread["config_version"] == "1.0"

    def test_write_config_creates_backup(self, svc, project_dir):
        cfg = svc.read_config()
        cfg["server_host"] = "0.0.0.0"
        svc.write_config(cfg, backup=True)
        backups = list(project_dir.glob("config.yaml.v*.bak"))
        assert len(backups) >= 1

    def test_write_config_validates_schema(self, svc):
        with pytest.raises(ValueError, match="Missing required key"):
            svc.write_config({"bad": "data"}, backup=False)

    def test_get_uptime(self, svc):
        uptime = svc.get_uptime()
        assert isinstance(uptime, float)
        assert uptime >= 0

    def test_config_status_false_when_missing(self, project_dir):
        from core.api.services import ApiService
        svc = ApiService()
        svc.config_path = project_dir / "nonexistent.yaml"
        assert svc.get_config_status() is False
