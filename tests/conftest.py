import logging
import os
import shutil
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Prevent Python from writing __pycache__ bytecode during tests, which
# would otherwise trigger the write guard when importing modules.
sys.dont_write_bytecode = True

# Ensure src/ is on sys.path so `import core.*` works.
_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

# Mock heavy dependencies before any test imports src.python.main.
_heavy = ["TikTokLive", "TikTokLive.events", "mcrcon", "flask"]
for _mod in _heavy:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Core modules import MCRconException by name and use it in `except` clauses;
# the mock needs a real exception class for those clauses to stay valid.
if "mcrcon" in sys.modules:
    sys.modules["mcrcon"].MCRconException = type("MCRconException", (Exception,), {})

from core.yaml_utils import save_yaml  # noqa: E402

MINIMAL_CONFIG = {
    "config_version": "1.0",
    "auto_update_config": True,
    "show_sudo_warning": False,
    "server_host": "127.0.0.1",
    "api_key": "",
    "control_method": "DCS",
    "shutdown": {},
    "java": {},
    "rcon": {},
    "tiktok": {},
    "comment_commands": {},
    "random_triggers": {},
    "console": {},
    "minecraft_server_api": {},
    "gui": {},
    "update": {},
    "overlay": {},
    "plugin_sandbox": {},
}

# ---------------------------------------------------------------------------
# Dedicated test workspace
# ---------------------------------------------------------------------------

TEST_WORKSPACE_ROOT = Path(__file__).resolve().parent / "workspace"
TEST_WORKSPACE_ROOT.mkdir(exist_ok=True)

logger = logging.getLogger("test_isolation")

# ---------------------------------------------------------------------------
# Write guard
# ---------------------------------------------------------------------------

from tests.guard import WriteGuard  # noqa: E402

_WRITE_GUARD = WriteGuard(
    allowed_roots={
        TEST_WORKSPACE_ROOT,
        Path(__file__).resolve().parent / ".pytest_cache",
        Path(__file__).resolve().parent.parent / ".pytest_cache",
    }
)


@pytest.fixture(scope="session", autouse=True)
def _activate_write_guard():
    """Activate the write guard for the entire test session."""
    _WRITE_GUARD.start()
    yield
    _WRITE_GUARD.stop()


# ---------------------------------------------------------------------------
# tmp_path override → tests/workspace/<session>/<test>/
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _session_workspace():
    """Create a session-scoped subdirectory under the test workspace."""
    # Clean up any stale session dirs from crashed previous runs
    for child in TEST_WORKSPACE_ROOT.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        elif child.is_file():
            child.unlink(missing_ok=True)

    session_id = f"session_{uuid.uuid4().hex}"
    path = TEST_WORKSPACE_ROOT / session_id
    path.mkdir(parents=True)
    logger.info("Created session workspace: %s", path)
    yield path
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    logger.info("Cleaned up session workspace: %s", path)


@pytest.fixture(scope="function")
def tmp_path(_session_workspace):
    """Override pytest's built-in *tmp_path* to use ``tests/workspace/<session>/."""
    test_id = f"test_{uuid.uuid4().hex}"
    path = _session_workspace / test_id
    path.mkdir(parents=True)
    logger.info("Created test workspace: %s", path)
    yield path
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    logger.info("Cleaned up test workspace: %s", path)


# ---------------------------------------------------------------------------
# project_dir — minimal project skeleton inside the test workspace
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def project_dir(tmp_path):
    """Create a minimal isolated project directory for the current test."""
    root = tmp_path / "project"
    root.mkdir()
    config_file = root / "config.yaml"
    save_yaml(config_file, MINIMAL_CONFIG, backup=False)
    (root / "data").mkdir()
    (root / "plugins").mkdir()
    (root / "src" / "plugins").mkdir(parents=True)
    (root / "core" / "runtime").mkdir(parents=True)
    (root / "templates").mkdir()
    (root / "static").mkdir()
    logger.info("Created project dir: %s", root)
    yield root


# ---------------------------------------------------------------------------
# Path patching — ALL core.paths functions are redirected to project_dir
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function", autouse=True)
def _patch_paths(project_dir):
    """Redirect every core.paths function into the isolated project_dir."""
    import core.api.registry
    import core.backup
    import core.overlay
    import core.overlay_utils
    import core.paths
    import core.secure_storage

    _orig = {
        "get_root_dir": core.paths.get_root_dir,
        "get_config_file": core.paths.get_config_file,
        "get_runtime_dir": core.paths.get_runtime_dir,
        "get_base_dir": core.paths.get_base_dir,
        "get_plugins_dir": core.paths.get_plugins_dir,
        "get_base_file": core.paths.get_base_file,
        "get_plugin_config_file": core.paths.get_plugin_config_file,
    }

    core.paths.get_root_dir = lambda: project_dir
    core.paths.get_config_file = lambda: project_dir / "config.yaml"
    core.paths.get_runtime_dir = lambda: project_dir / "core" / "runtime"
    core.paths.get_base_dir = lambda: project_dir / "src"
    core.paths.get_plugins_dir = lambda: project_dir / "src" / "plugins"
    core.paths.get_base_file = lambda: (
        core.paths.get_base_dir() / f"main{core.paths.SUFFIX}"
    )
    core.paths.get_plugin_config_file = lambda: project_dir / "src" / "config.yaml"

    # Propagate patches to every module that did ``from core.paths import ...``
    # (those create local bindings that are NOT affected by mutating core.paths).
    _orig_funcs = {
        n: _orig[n]
        for n in (
            "get_root_dir",
            "get_config_file",
            "get_runtime_dir",
            "get_base_dir",
            "get_plugins_dir",
            "get_base_file",
            "get_plugin_config_file",
        )
    }
    _new_funcs = {n: getattr(core.paths, n) for n in _orig_funcs}
    for mod_name, mod in list(sys.modules.items()):
        if mod is None or not hasattr(mod, "__dict__"):
            continue
        for name, orig in _orig_funcs.items():
            if getattr(mod, name, None) is orig:
                setattr(mod, name, _new_funcs[name])

    # Reset singletons so they recreate with the new paths on next access.
    try:
        import core.api.registry

        core.api.registry._registry = None
    except Exception:
        pass
    try:
        core.backup._backup_manager = None
    except Exception:
        pass
    try:
        core.overlay._manager = None
    except Exception:
        pass
    try:
        core.overlay_utils._manager = None
    except Exception:
        pass

    # Reset cached service instances in API route modules so that
    # ApiService, ActionsService, etc. are recreated with patched paths.
    for mod_name in (
        "core.api.routes.config",
        "core.api.routes.health",
        "core.api.routes.rcon",
        "core.api.routes.versions",
        "core.api.routes.actions",
    ):
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            if hasattr(mod, "_service"):
                mod._service = None
            if hasattr(mod, "_api_service"):
                mod._api_service = None

    # Patch the module-level cached runtime dir in reload.py if it has
    # already been imported in a previous test.
    if "core.api.routes.reload" in sys.modules:
        sys.modules["core.api.routes.reload"]._RUNTIME_DIR = (
            project_dir / "core" / "runtime"
        )

    logger.info("Patched paths to project_dir: %s", project_dir)

    yield

    # Restore core.paths functions
    for name, fn in _orig.items():
        setattr(core.paths, name, fn)

    # Restore local bindings in loaded modules
    for mod_name, mod in list(sys.modules.items()):
        if mod is None or not hasattr(mod, "__dict__"):
            continue
        for name, orig in _orig_funcs.items():
            if getattr(mod, name, None) is _new_funcs[name]:
                setattr(mod, name, orig)

    logger.info("Restored original paths")


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def client():
    from core.api import create_app

    app = create_app()
    with TestClient(app) as tc:
        yield tc


# ---------------------------------------------------------------------------
# Session-level filesystem snapshot for post-hoc isolation verification
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _session_isolation_snapshot(request):
    """Record a snapshot of the project tree at session start."""
    project_root = Path(__file__).resolve().parent.parent

    def _snapshot():
        snap = {}
        for p in project_root.rglob("*"):
            if not p.is_file():
                continue
            try:
                rel = p.relative_to(project_root)
            except ValueError:
                continue
            # Skip the test workspace, pytest cache, git, pycache, etc.
            skip = False
            for part in rel.parts:
                if part in (
                    ".git",
                    ".pytest_cache",
                    "workspace",
                    "__pycache__",
                    ".tmp_path_factory",
                ):
                    skip = True
                    break
            if skip:
                continue
            try:
                stat = p.stat()
                snap[str(rel)] = (stat.st_size, stat.st_mtime_ns)
            except OSError:
                pass
        return snap

    before = _snapshot()
    request.config.stash["isolation_snapshot_before"] = before
    request.config.stash["isolation_project_root"] = project_root
    yield


# ---------------------------------------------------------------------------
# Ensure the safety test runs last
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(config, items):
    """Move isolation-safety tests to the end of the run."""
    safety = [item for item in items if "test_isolation_safety" in item.nodeid]
    for item in safety:
        items.remove(item)
        items.append(item)
