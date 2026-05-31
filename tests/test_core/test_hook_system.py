import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def clean_registry():
    from core.hook_api import HOOK_ACTIONS

    prev = dict(HOOK_ACTIONS)
    HOOK_ACTIONS.clear()
    yield HOOK_ACTIONS
    HOOK_ACTIONS.clear()
    HOOK_ACTIONS.update(prev)


@pytest.fixture
def hooks_dir():
    base = Path(__file__).resolve().parent.parent.parent
    return (base / "src" / "hooks").resolve()


def test_hooks_directory_exists(hooks_dir):
    assert hooks_dir.exists(), f"Hooks directory not found: {hooks_dir}"


def test_hooks_directory_has_hook_dirs(hooks_dir):
    """Hooks are now subdirectories with main.py (not flat .py files)."""
    hook_dirs = [d for d in hooks_dir.iterdir() if d.is_dir()]
    assert len(hook_dirs) > 0, f"No hook subdirectories in: {hooks_dir}"


def test_each_hook_dir_has_main_py(hooks_dir):
    for d in sorted(hooks_dir.iterdir()):
        if d.is_dir() and d.name != "__pycache__":
            main_py = d / "main.py"
            assert main_py.exists(), f"Missing main.py in hook dir: {d}"


def test_each_hook_dir_has_hook_json(hooks_dir):
    for d in sorted(hooks_dir.iterdir()):
        if d.is_dir() and d.name != "__pycache__":
            hook_json = d / "hook.json"
            assert hook_json.exists(), f"Missing hook.json in hook dir: {d}"


def test_hook_registration(clean_registry, hooks_dir):
    from core.hook_loader import load_event_hooks
    from core.hook_api import HookAPI
    import asyncio

    loop = asyncio.new_event_loop()
    rcon_queue = asyncio.Queue()
    trigger_queue = asyncio.Queue()
    config = {}
    valid_functions = set()

    api = HookAPI(rcon_queue, trigger_queue, loop, config, valid_functions)
    load_event_hooks(api, hooks_dir, config=config)

    assert len(clean_registry) > 0, "No scripts were registered"
    for name in clean_registry:
        assert callable(clean_registry[name]), f"Handler for '{name}' is not callable"


def test_registration_names_are_strings(clean_registry, hooks_dir):
    from core.hook_loader import load_event_hooks
    from core.hook_api import HookAPI
    import asyncio

    loop = asyncio.new_event_loop()
    api = HookAPI(asyncio.Queue(), asyncio.Queue(), loop, {}, set())
    load_event_hooks(api, hooks_dir, config={})

    for name in clean_registry:
        assert isinstance(name, str), f"Registration name is not a string: {name!r}"


def test_registration_names_are_nonempty(clean_registry, hooks_dir):
    from core.hook_loader import load_event_hooks
    from core.hook_api import HookAPI
    import asyncio

    loop = asyncio.new_event_loop()
    api = HookAPI(asyncio.Queue(), asyncio.Queue(), loop, {}, set())
    load_event_hooks(api, hooks_dir, config={})

    for name in clean_registry:
        assert name.strip(), f"Registration name is empty or whitespace: {name!r}"


def test_duplicate_registration_is_ignored(clean_registry, hooks_dir):
    from core.hook_loader import load_event_hooks
    from core.hook_api import HookAPI, HOOK_ACTIONS
    import asyncio

    loop = asyncio.new_event_loop()
    api = HookAPI(asyncio.Queue(), asyncio.Queue(), loop, {}, set())
    load_event_hooks(api, hooks_dir, config={})

    original_count = len(HOOK_ACTIONS)

    api.register_action("test_dup", lambda u, t, c: None)
    assert len(HOOK_ACTIONS) == original_count + 1

    api.register_action("test_dup", lambda u, t, c: None)
    assert len(HOOK_ACTIONS) == original_count + 1


def test_invalid_name_is_rejected(clean_registry):
    from core.hook_api import HookAPI, HOOK_ACTIONS
    import asyncio

    api = HookAPI(asyncio.Queue(), asyncio.Queue(), asyncio.new_event_loop(), {}, set())
    api.register_action("", lambda u, t, c: None)
    assert "" not in HOOK_ACTIONS

    api.register_action("   ", lambda u, t, c: None)
    assert "   " not in HOOK_ACTIONS


def test_api_response_format_matches_endpoint(clean_registry, hooks_dir):
    from core.hook_loader import load_event_hooks
    from core.hook_api import HookAPI, HOOK_ACTIONS
    import asyncio

    loop = asyncio.new_event_loop()
    api = HookAPI(asyncio.Queue(), asyncio.Queue(), loop, {}, set())
    load_event_hooks(api, hooks_dir, config={})

    scripts = [{"name": name} for name in sorted(HOOK_ACTIONS.keys())]
    response = {"scripts": scripts}

    assert "scripts" in response
    assert isinstance(response["scripts"], list)
    if response["scripts"]:
        assert "name" in response["scripts"][0]


def test_spotify_hook_exists_in_plugin_dir():
    """Spotify hook moved to plugins/spotify/hooks/spotify_control/."""
    base = Path(__file__).resolve().parent.parent.parent
    spotify_hook = base / "src" / "plugins" / "spotify" / "hooks" / "spotify_control" / "main.py"
    assert spotify_hook.exists(), f"Spotify hook not found: {spotify_hook}"


def test_spotify_hook_manifest_exists():
    base = Path(__file__).resolve().parent.parent.parent
    manifest = base / "src" / "plugins" / "spotify" / "hooks" / "spotify_control" / "hook.json"
    assert manifest.exists(), f"Spotify hook manifest not found: {manifest}"


def test_hook_api_get_hook_config():
    from core.hook_api import HookAPI
    import asyncio

    loop = asyncio.new_event_loop()
    api = HookAPI(
        asyncio.Queue(), asyncio.Queue(), loop, {},
        set(),
        hook_configs={"test_hook": {"mode": "deny-all", "triggers": ["foo"]}},
    )

    cfg = api.get_hook_config("test_hook")
    assert cfg == {"mode": "deny-all", "triggers": ["foo"]}

    cfg_missing = api.get_hook_config("nonexistent")
    assert cfg_missing == {}
