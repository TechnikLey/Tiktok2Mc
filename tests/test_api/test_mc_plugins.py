class TestMcPluginsList:
    def test_list_plugins_empty_when_no_plugins_dir(self, client, project_dir):
        server_dir = project_dir / "server" / "default"
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "server.jar").write_bytes(b"fake jar")

        resp = client.get("/api/v1/server/default/mc-plugins")
        assert resp.status_code == 200
        assert resp.json()["plugins"] == []

    def test_list_plugins_returns_empty_for_nonexistent_instance(
        self, client, project_dir
    ):
        resp = client.get("/api/v1/server/nonexistent/mc-plugins")
        assert resp.status_code == 404

    def test_list_plugins_returns_empty_when_no_jar(self, client, project_dir):
        resp = client.get("/api/v1/server/default/mc-plugins")
        assert resp.status_code == 404

    def test_list_plugins_after_jar_installed(self, client, project_dir):
        server_dir = project_dir / "server" / "default"
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "server.jar").write_bytes(b"fake jar")
        plugins_dir = server_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)

        resp = client.get("/api/v1/server/default/mc-plugins")
        assert resp.status_code == 200
        assert resp.json()["plugins"] == []

    def test_list_plugins_detects_enabled(self, client, project_dir):
        server_dir = project_dir / "server" / "default"
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "server.jar").write_bytes(b"fake jar")
        plugins_dir = server_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        (plugins_dir / "EssentialsX.jar").write_bytes(b"plugin")

        resp = client.get("/api/v1/server/default/mc-plugins")
        assert resp.status_code == 200
        plugins = resp.json()["plugins"]
        assert len(plugins) == 1
        assert plugins[0]["name"] == "EssentialsX"
        assert plugins[0]["enabled"] is True

    def test_list_plugins_detects_disabled(self, client, project_dir):
        server_dir = project_dir / "server" / "default"
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "server.jar").write_bytes(b"fake jar")
        plugins_dir = server_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        (plugins_dir / "EssentialsX.jar.disabled").write_bytes(b"plugin")

        resp = client.get("/api/v1/server/default/mc-plugins")
        assert resp.status_code == 200
        plugins = resp.json()["plugins"]
        assert len(plugins) == 1
        assert plugins[0]["name"] == "EssentialsX"
        assert plugins[0]["enabled"] is False

    def test_list_plugins_mixed(self, client, project_dir):
        server_dir = project_dir / "server" / "default"
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "server.jar").write_bytes(b"fake jar")
        plugins_dir = server_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        (plugins_dir / "PluginA.jar").write_bytes(b"a")
        (plugins_dir / "PluginB.jar.disabled").write_bytes(b"b")

        resp = client.get("/api/v1/server/default/mc-plugins")
        assert resp.status_code == 200
        plugins = resp.json()["plugins"]
        assert len(plugins) == 2
        names = {p["name"] for p in plugins}
        assert names == {"PluginA", "PluginB"}

    def test_list_plugins_ignores_subdirs(self, client, project_dir):
        server_dir = project_dir / "server" / "default"
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "server.jar").write_bytes(b"fake jar")
        plugins_dir = server_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        (plugins_dir / "SubDir").mkdir()
        (plugins_dir / "RealPlugin.jar").write_bytes(b"plugin")

        resp = client.get("/api/v1/server/default/mc-plugins")
        assert resp.status_code == 200
        plugins = resp.json()["plugins"]
        assert len(plugins) == 1
        assert plugins[0]["name"] == "RealPlugin"


class TestMcPluginsEnable:
    def _setup(self, project_dir):
        server_dir = project_dir / "server" / "default"
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "server.jar").write_bytes(b"fake jar")
        plugins_dir = server_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        return plugins_dir

    def test_enable_disabled_plugin(self, client, project_dir):
        plugins_dir = self._setup(project_dir)
        (plugins_dir / "MyPlugin.jar.disabled").write_bytes(b"plugin")

        resp = client.post("/api/v1/server/default/mc-plugins/MyPlugin/enable")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "enabled"
        assert body["enabled"] is True
        assert (plugins_dir / "MyPlugin.jar").exists()
        assert not (plugins_dir / "MyPlugin.jar.disabled").exists()

    def test_enable_already_enabled_plugin(self, client, project_dir):
        plugins_dir = self._setup(project_dir)
        (plugins_dir / "MyPlugin.jar").write_bytes(b"plugin")

        resp = client.post("/api/v1/server/default/mc-plugins/MyPlugin/enable")
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_enabled"

    def test_enable_nonexistent_plugin(self, client, project_dir):
        self._setup(project_dir)
        resp = client.post("/api/v1/server/default/mc-plugins/Nonexistent/enable")
        assert resp.status_code == 404

    def test_enable_plugin_strips_jar_extension(self, client, project_dir):
        plugins_dir = self._setup(project_dir)
        (plugins_dir / "TestPlugin.jar.disabled").write_bytes(b"plugin")

        resp = client.post("/api/v1/server/default/mc-plugins/TestPlugin.jar/enable")
        assert resp.status_code == 200
        assert (plugins_dir / "TestPlugin.jar").exists()


class TestMcPluginsDisable:
    def _setup(self, project_dir):
        server_dir = project_dir / "server" / "default"
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "server.jar").write_bytes(b"fake jar")
        plugins_dir = server_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        return plugins_dir

    def test_disable_enabled_plugin(self, client, project_dir):
        plugins_dir = self._setup(project_dir)
        (plugins_dir / "MyPlugin.jar").write_bytes(b"plugin")

        resp = client.post("/api/v1/server/default/mc-plugins/MyPlugin/disable")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "disabled"
        assert body["enabled"] is False
        assert (plugins_dir / "MyPlugin.jar.disabled").exists()
        assert not (plugins_dir / "MyPlugin.jar").exists()

    def test_disable_already_disabled_plugin(self, client, project_dir):
        plugins_dir = self._setup(project_dir)
        (plugins_dir / "MyPlugin.jar.disabled").write_bytes(b"plugin")

        resp = client.post("/api/v1/server/default/mc-plugins/MyPlugin/disable")
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_disabled"

    def test_disable_nonexistent_plugin(self, client, project_dir):
        self._setup(project_dir)
        resp = client.post("/api/v1/server/default/mc-plugins/Nonexistent/disable")
        assert resp.status_code == 404


class TestMcPluginsDelete:
    def _setup(self, project_dir):
        server_dir = project_dir / "server" / "default"
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "server.jar").write_bytes(b"fake jar")
        plugins_dir = server_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        return plugins_dir

    def test_delete_enabled_plugin(self, client, project_dir):
        plugins_dir = self._setup(project_dir)
        (plugins_dir / "OldPlugin.jar").write_bytes(b"plugin")

        resp = client.delete("/api/v1/server/default/mc-plugins/OldPlugin")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert not (plugins_dir / "OldPlugin.jar").exists()

    def test_delete_disabled_plugin(self, client, project_dir):
        plugins_dir = self._setup(project_dir)
        (plugins_dir / "OldPlugin.jar.disabled").write_bytes(b"plugin")

        resp = client.delete("/api/v1/server/default/mc-plugins/OldPlugin")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert not (plugins_dir / "OldPlugin.jar.disabled").exists()

    def test_delete_nonexistent_plugin(self, client, project_dir):
        self._setup(project_dir)
        resp = client.delete("/api/v1/server/default/mc-plugins/Nonexistent")
        assert resp.status_code == 404

    def test_delete_plugin_nonexistent_instance(self, client, project_dir):
        resp = client.delete("/api/v1/server/nonexistent/mc-plugins/SomePlugin")
        assert resp.status_code == 404


class TestMcPluginsUpload:
    def _setup(self, project_dir):
        server_dir = project_dir / "server" / "default"
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "server.jar").write_bytes(b"fake jar")
        plugins_dir = server_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        return plugins_dir

    def test_upload_jar(self, client, project_dir):
        self._setup(project_dir)
        resp = client.post(
            "/api/v1/server/default/mc-plugins/upload",
            files={
                "file": (
                    "EssentialsX.jar",
                    b"plugin-content",
                    "application/java-archive",
                )
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "uploaded"
        assert data["plugin"] == "EssentialsX"
        plugins_dir = project_dir / "server" / "default" / "plugins"
        assert (plugins_dir / "EssentialsX.jar").exists()

    def test_upload_non_jar_rejected(self, client, project_dir):
        self._setup(project_dir)
        resp = client.post(
            "/api/v1/server/default/mc-plugins/upload",
            files={"file": ("readme.txt", b"text", "text/plain")},
        )
        assert resp.status_code == 400

    def test_upload_nonexistent_instance(self, client, project_dir):
        resp = client.post(
            "/api/v1/server/nonexistent/mc-plugins/upload",
            files={"file": ("Plugin.jar", b"content", "application/java-archive")},
        )
        assert resp.status_code == 404

    def test_upload_creates_plugins_dir(self, client, project_dir):
        server_dir = project_dir / "server" / "default"
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "server.jar").write_bytes(b"fake jar")
        resp = client.post(
            "/api/v1/server/default/mc-plugins/upload",
            files={"file": ("Dynmap.jar", b"plugin", "application/java-archive")},
        )
        assert resp.status_code == 200
        assert (server_dir / "plugins" / "Dynmap.jar").exists()
