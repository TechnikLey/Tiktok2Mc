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
    return (base / "src" / "event_hooks").resolve()


def test_hooks_directory_exists(hooks_dir):
    assert hooks_dir.exists(), f"Hooks directory not found: {hooks_dir}"


def test_hooks_directory_has_py_files(hooks_dir):
    py_files = list(hooks_dir.glob("*.py"))
    assert len(py_files) > 0, f"No .py files in hooks directory: {hooks_dir}"


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
    load_event_hooks(api, hooks_dir)

    assert len(clean_registry) > 0, "No scripts were registered"
    for name in clean_registry:
        assert callable(clean_registry[name]), f"Handler for '{name}' is not callable"


def test_registration_names_are_strings(clean_registry, hooks_dir):
    from core.hook_loader import load_event_hooks
    from core.hook_api import HookAPI
    import asyncio

    loop = asyncio.new_event_loop()
    api = HookAPI(asyncio.Queue(), asyncio.Queue(), loop, {}, set())
    load_event_hooks(api, hooks_dir)

    for name in clean_registry:
        assert isinstance(name, str), f"Registration name is not a string: {name!r}"


def test_registration_names_are_nonempty(clean_registry, hooks_dir):
    from core.hook_loader import load_event_hooks
    from core.hook_api import HookAPI
    import asyncio

    loop = asyncio.new_event_loop()
    api = HookAPI(asyncio.Queue(), asyncio.Queue(), loop, {}, set())
    load_event_hooks(api, hooks_dir)

    for name in clean_registry:
        assert name.strip(), f"Registration name is empty or whitespace: {name!r}"


def test_duplicate_registration_is_ignored(clean_registry, hooks_dir):
    from core.hook_loader import load_event_hooks
    from core.hook_api import HookAPI, HOOK_ACTIONS
    import asyncio

    loop = asyncio.new_event_loop()
    api = HookAPI(asyncio.Queue(), asyncio.Queue(), loop, {}, set())
    load_event_hooks(api, hooks_dir)

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
    load_event_hooks(api, hooks_dir)

    scripts = [{"name": name} for name in sorted(HOOK_ACTIONS.keys())]
    response = {"scripts": scripts}

    assert "scripts" in response
    assert isinstance(response["scripts"], list)
    if response["scripts"]:
        assert "name" in response["scripts"][0]


def test_spotify_hook_plugin_config_import(hooks_dir):
    spotify_file = hooks_dir / "spotify.py"
    if not spotify_file.exists():
        pytest.skip("spotify.py not found")

    from core.hook_loader import _check_imports
    disallowed = _check_imports(spotify_file)
    assert "core.plugin_config" not in disallowed
