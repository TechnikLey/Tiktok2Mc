

class TestServersList:
    def test_default_instance_reports_missing_jar(self, client, project_dir):
        resp = client.get("/api/v1/servers")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["instances"]) >= 1
        default = next(i for i in body["instances"] if i["id"] == "default")
        assert default["hasJar"] is False

    def test_instance_reports_jar_after_installation(self, client, project_dir):
        jar_dir = project_dir / "server" / "default"
        jar_dir.mkdir(parents=True, exist_ok=True)
        (jar_dir / "server.jar").write_bytes(b"fake jar content")

        resp = client.get("/api/v1/servers")
        assert resp.status_code == 200
        body = resp.json()
        default = next(i for i in body["instances"] if i["id"] == "default")
        assert default["hasJar"] is True

    def test_get_instance_includes_has_jar(self, client, project_dir):
        resp = client.get("/api/v1/servers/instances/default")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "default"
        assert "hasJar" in body
        assert body["hasJar"] is False
