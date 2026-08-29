class TestBackupsList:
    def test_list_empty_when_no_backups(self, client):
        resp = client.get("/api/v1/backups")
        assert resp.status_code == 200
        body = resp.json()
        assert body["categories"] == []
        assert body["total"] == 0
        assert "backups" in body["root"]

    def test_list_shows_config_category_after_save(self, client, project_dir):
        _update_config(client, {"server_host": "0.0.0.1"})
        resp = client.get("/api/v1/backups")
        assert resp.status_code == 200
        cats = {c["category"]: c for c in resp.json()["categories"]}
        assert "config" in cats
        assert cats["config"]["count"] >= 1
        entry = cats["config"]["entries"][0]
        assert entry["filename"].startswith("config.v")
        assert entry["filename"].endswith(".yaml.bak")
        assert entry["label"]  # parsed timestamp
        assert entry["size"] > 0
        assert entry["restorable"] is True
        assert (project_dir / "data" / "backups" / "config").is_dir()

    def test_list_actions_category_after_save(self, client, project_dir):
        # First write creates the file; the second write creates the backup
        for _ in range(2):
            resp = client.put(
                "/api/v1/actions",
                json={
                    "triggers": [
                        {
                            "name": "follow",
                            "enabled": True,
                            "type": "Custom",
                            "commands": [{"type": "vanilla", "command": "say hi"}],
                        }
                    ]
                },
            )
            assert resp.status_code == 200
        resp = client.get("/api/v1/backups")
        cats = {c["category"] for c in resp.json()["categories"]}
        assert "actions" in cats

    def test_list_plugin_category(self, client, project_dir):
        plugin_cfg = project_dir / "src" / "plugins" / "testplugin" / "config.yaml"
        plugin_cfg.parent.mkdir(parents=True, exist_ok=True)
        plugin_cfg.write_text("enabled: true\n", encoding="utf-8")

        from core.backup import get_backup_manager

        get_backup_manager().create_backup(plugin_cfg, category="plugins/testplugin")

        resp = client.get("/api/v1/backups")
        assert resp.status_code == 200
        cats = {c["category"]: c for c in resp.json()["categories"]}
        assert "plugins/testplugin" in cats
        assert cats["plugins/testplugin"]["entries"][0]["restorable"] is True

    def test_list_marks_unknown_category_not_restorable(self, client, project_dir):
        from core.backup import get_backup_manager

        root = project_dir / "data"
        root.mkdir(exist_ok=True)
        source = root / "gifts.json"
        source.write_text("[]", encoding="utf-8")
        get_backup_manager().create_backup(source)  # -> category "_other"

        resp = client.get("/api/v1/backups")
        cats = {c["category"]: c for c in resp.json()["categories"]}
        assert "_other" in cats
        assert cats["_other"]["entries"][0]["restorable"] is False


class TestBackupsRestore:
    def test_restore_config_reverts_changes(self, client):
        current = client.get("/api/v1/config").json()["config"]
        original_host = current["server_host"]

        _update_config(client, {"server_host": "10.0.0.1"})
        assert (
            client.get("/api/v1/config").json()["config"]["server_host"] == "10.0.0.1"
        )

        backup = _newest_backup(client, "config")
        resp = client.post(
            "/api/v1/backups/restore",
            json={"category": "config", "filename": backup["filename"]},
        )
        assert resp.status_code == 200
        assert resp.json()["target"].endswith("config.yaml")

        restored = client.get("/api/v1/config").json()["config"]["server_host"]
        assert restored == original_host

    def test_restore_unknown_category_400(self, client):
        resp = client.post(
            "/api/v1/backups/restore",
            json={"category": "nope", "filename": "x.bak"},
        )
        assert resp.status_code == 400

    def test_restore_traversal_filename_400(self, client):
        resp = client.post(
            "/api/v1/backups/restore",
            json={"category": "config", "filename": "../config.yaml"},
        )
        assert resp.status_code == 400

    def test_restore_category_traversal_400(self, client):
        resp = client.post(
            "/api/v1/backups/restore",
            json={"category": "../../evil", "filename": "x.bak"},
        )
        assert resp.status_code == 400

    def test_restore_custom_target_sibling_escape_400(self, client):
        # "../Tiktok2Mc-sibling/..." starts with the project root as a
        # string but resolves to a sibling directory — must be rejected.
        resp = client.post(
            "/api/v1/backups/restore",
            json={
                "category": "_other",
                "filename": "x.bak",
                "target": "../Tiktok2Mc-sibling/evil.yaml",
            },
        )
        assert resp.status_code == 400

    def test_restore_missing_file_400(self, client):
        resp = client.post(
            "/api/v1/backups/restore",
            json={
                "category": "config",
                "filename": "config.v20000101_000000_000000.yaml.bak",
            },
        )
        assert resp.status_code == 400

    def test_restore_other_with_custom_target(self, client, project_dir):
        from core.backup import get_backup_manager

        root = project_dir / "data"
        root.mkdir(exist_ok=True)
        source = root / "gifts.json"
        source.write_text("[]", encoding="utf-8")
        get_backup_manager().create_backup(source)

        target = project_dir / "data" / "restored_gifts.json"
        resp = client.post(
            "/api/v1/backups/restore",
            json={
                "category": "_other",
                "filename": source.name + ".bak",
                "target": "data/restored_gifts.json",
            },
        )
        # The filename may have a versioned name, so find it from the listing
        listed = client.get("/api/v1/backups").json()
        other_cat = next(
            (c for c in listed["categories"] if c["category"] == "_other"), None
        )
        assert other_cat is not None
        bak_name = other_cat["entries"][0]["filename"]
        resp = client.post(
            "/api/v1/backups/restore",
            json={
                "category": "_other",
                "filename": bak_name,
                "target": "data/restored_gifts.json",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["target"].endswith("restored_gifts.json")
        assert target.exists()

    def test_restore_other_without_target_400(self, client, project_dir):
        from core.backup import get_backup_manager

        root = project_dir / "data"
        root.mkdir(exist_ok=True)
        source = root / "gifts.json"
        source.write_text("[]", encoding="utf-8")
        get_backup_manager().create_backup(source)

        listed = client.get("/api/v1/backups").json()
        other_cat = next(
            (c for c in listed["categories"] if c["category"] == "_other"), None
        )
        assert other_cat is not None
        bak_name = other_cat["entries"][0]["filename"]
        resp = client.post(
            "/api/v1/backups/restore",
            json={"category": "_other", "filename": bak_name},
        )
        assert resp.status_code == 400

    def test_restore_custom_target_escape_400(self, client, project_dir):
        from core.backup import get_backup_manager

        root = project_dir / "data"
        root.mkdir(exist_ok=True)
        source = root / "gifts.json"
        source.write_text("[]", encoding="utf-8")
        get_backup_manager().create_backup(source)

        listed = client.get("/api/v1/backups").json()
        other_cat = next(
            (c for c in listed["categories"] if c["category"] == "_other"), None
        )
        assert other_cat is not None
        bak_name = other_cat["entries"][0]["filename"]
        resp = client.post(
            "/api/v1/backups/restore",
            json={
                "category": "_other",
                "filename": bak_name,
                "target": "../../etc/passwd",
            },
        )
        assert resp.status_code == 400


class TestBackupsCreate:
    def test_create_config_and_actions(self, client, project_dir):
        (project_dir / "data" / "actions.mca").write_text(
            "# test\nfollow:/say hi\n", encoding="utf-8"
        )
        resp = client.post(
            "/api/v1/backups/create", json={"targets": ["config", "actions"]}
        )
        assert resp.status_code == 200
        body = resp.json()
        created = {c["target"] for c in body["created"]}
        assert "config" in created
        assert "actions" in created

        listed = client.get("/api/v1/backups").json()["categories"]
        cats = {c["category"] for c in listed}
        assert "config" in cats
        assert "actions" in cats

    def test_create_skips_unknown_target(self, client):
        resp = client.post("/api/v1/backups/create", json={"targets": ["wat"]})
        assert resp.status_code == 200
        assert resp.json()["created"] == []
        assert "wat" in resp.json()["skipped"]


def _update_config(client, patch):
    current = client.get("/api/v1/config").json()
    cfg = current["config"].copy()
    cfg.update(patch)
    resp = client.put("/api/v1/config", json={"config": cfg, "backup": True})
    assert resp.status_code == 200
    return resp


def _newest_backup(client, category):
    resp = client.get("/api/v1/backups")
    assert resp.status_code == 200
    for c in resp.json()["categories"]:
        if c["category"] == category:
            assert c["entries"], f"no backups in category {category}"
            return c["entries"][0]
    raise AssertionError(f"category {category} not found")
