#!/usr/bin/env python3
# ==========================================
# build.py - TikTok-MC-Gift (Parallel & Cross-Platform)
#
# Usage:
#   python build.py <command> [options]
#
# Commands:
#   app              Build application (PyInstaller); use --only to build select .py files
#   vsix             Build VS Code extension (.vsix)
#   spec             Generate MCA language specification
#   test             Run tests (MCA / Python)
#   all              Run spec + app + vsix
#   ci               CI pipeline (validate + test + spec + app)
#   clean            Clean build artifacts
# ==========================================

import argparse
import ast
import fnmatch
import hashlib
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)


# ---- Colors (ANSI, works on modern Windows 10+ and Linux) ----
class Color:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    RESET = "\033[0m"


def cprint(msg, color=Color.RESET):
    log.info(f"{color}{msg}{Color.RESET}")


def _task_matches(task: dict, token: str) -> bool:
    """Check whether a build task matches a user-supplied ``--only`` token.

    Tokens may be given as:
      - task/executable name or its stem   (``server``, ``server.exe``)
      - the .py source basename            (``server.py``)
      - a source path relative to the root (``src/python/server.py``)
    """
    t = token.strip().replace("\\", "/").lower()
    if not t:
        return False
    src = task["src"].replace("\\", "/").lower()
    name = task["name"].lower()
    stem = Path(task["name"]).stem.lower()
    src_stem = Path(task["src"]).stem.lower()
    if t == name or t == stem or t == src_stem:
        return True
    if t.endswith(".py"):
        return src == t or src.endswith("/" + t)
    return src == t + ".py" or src.endswith("/" + t + ".py")


def _filter_build_tasks(
    all_build_tasks: list[dict], tokens: list[str]
) -> tuple[list[dict], list[str], list[str]]:
    """Filter build tasks by ``--only`` tokens.

    Returns ``(kept_tasks, matched_names, unmatched_tokens)``.
    """
    clean = [t.strip() for t in tokens if t and t.strip()]
    keep: list[dict] = []
    matched_names: set[str] = set()
    for task in all_build_tasks:
        if any(_task_matches(task, t) for t in clean):
            keep.append(task)
            matched_names.add(task["name"])
    unmatched = [
        t for t in clean if not any(_task_matches(task, t) for task in all_build_tasks)
    ]
    return keep, sorted(matched_names), unmatched


def _kill_proc_tree(pid):
    """Kill a process and all descendants (Windows)."""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                check=False,
                capture_output=True,
            )
        except Exception:
            pass


# Enable ANSI colors on Windows
if sys.platform == "win32":
    os.system("")  # enables ANSI escape sequences in Windows terminal

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from core.version import TOOL_VERSION, UPDATER_VERSION  # noqa: E402

# ── MCA spec sources and paths
MCA_SPEC_SOURCES = [
    "src/core/validator.py",
    "src/core/api/services/actions.py",
    "tools/generate_mca_spec.py",
]
MCA_SPEC_OUTPUT = "mca-language-server/mca-spec.json"
MCA_EXTENSION_DIR = "mca-language-server"
MCA_SERVER_TEST_DIR = "mca-language-server/server/test"


def _spec_source_hashes() -> dict[str, str]:
    """Return {relative_path: sha256} for all files that feed into the MCA spec."""
    hashes = {}
    for rel in MCA_SPEC_SOURCES:
        p = Path(__file__).resolve().parent / rel
        if p.exists():
            hashes[rel] = _sha256_file(p)
        else:
            hashes[rel] = ""
    return hashes


def _sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _generate_mca_spec(force: bool = False) -> bool:
    """Generate MCA language spec JSON from Python sources.

    Returns True if the spec was generated (or was already current).
    Raises RuntimeError on failure.
    """
    script = Path(__file__).resolve().parent / "tools" / "generate_mca_spec.py"
    if not script.exists():
        raise RuntimeError(f"MCA spec generator not found: {script}")

    # Incremental: check if any source file has changed
    if not force:
        cache = (
            Path(__file__).resolve().parent / "build" / "cache" / "mca_spec_hashes.json"
        )
        current_hashes = _spec_source_hashes()
        if cache.exists():
            try:
                cached = json.loads(cache.read_text(encoding="utf-8"))
                if cached.get("hashes") == current_hashes:
                    output = Path(__file__).resolve().parent / MCA_SPEC_OUTPUT
                    if output.exists():
                        cprint("MCA spec up to date (no source changes).", Color.GRAY)
                        return True
            except Exception:
                pass

    cprint("Generating MCA language specification...", Color.CYAN)
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"MCA spec generation failed:\n{result.stderr.strip()}")
    for line in result.stdout.strip().split("\n"):
        cprint(f"  {line}", Color.GRAY)

    # Persist hash cache for incremental builds
    cache = Path(__file__).resolve().parent / "build" / "cache" / "mca_spec_hashes.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps({"hashes": _spec_source_hashes()}, indent=2),
        encoding="utf-8",
    )
    return True


def _validate_mca_spec() -> None:
    """Validate that the generated mca-spec.json is correct.

    Raises RuntimeError if validation fails.
    """
    spec_path = Path(__file__).resolve().parent / MCA_SPEC_OUTPUT
    if not spec_path.exists():
        raise RuntimeError(f"MCA spec not found: {spec_path}")

    try:
        data = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"MCA spec is not valid JSON: {e}")

    required = [
        "version",
        "event_triggers",
        "command_prefixes",
        "diagnostic_codes",
        "placeholders",
        "patterns",
        "validation_rules",
    ]
    missing = [k for k in required if k not in data]
    if missing:
        raise RuntimeError(f"MCA spec missing required fields: {', '.join(missing)}")

    if (
        not isinstance(data.get("event_triggers"), list)
        or len(data["event_triggers"]) == 0
    ):
        raise RuntimeError("MCA spec: event_triggers must be a non-empty list")

    if (
        not isinstance(data.get("command_prefixes"), dict)
        or len(data["command_prefixes"]) == 0
    ):
        raise RuntimeError("MCA spec: command_prefixes must be a non-empty dict")

    if (
        not isinstance(data.get("diagnostic_codes"), list)
        or len(data["diagnostic_codes"]) == 0
    ):
        raise RuntimeError("MCA spec: diagnostic_codes must be a non-empty list")

    cprint("MCA specification valid.", Color.GRAY)


def _run_python_tests() -> None:
    """Run the full Python test suite via pytest.

    Raises RuntimeError if any test fails.
    """
    try:
        import importlib.util

        if importlib.util.find_spec("pytest") is None:
            raise ImportError
    except ImportError:
        raise RuntimeError(
            "pytest is not installed.\nInstall it: pip install pytest pytest-timeout"
        )

    cprint("Running Python test suite...", Color.CYAN)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-x",
            "--timeout=60",
            "-p",
            "no:randomly",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    stdout_lines: list[str] = []
    for line in proc.stdout or []:
        stdout_lines.append(line)
        stripped = line.rstrip("\n")
        if not stripped:
            continue
        if "FAILED" in stripped or "FAIL" in stripped and "PASS" not in stripped:
            cprint(stripped, Color.RED)
        elif "warning" in stripped.lower() or "Warning" in stripped:
            cprint(stripped, Color.YELLOW)
        elif "error" in stripped.lower():
            cprint(stripped, Color.RED)
        elif stripped.startswith("tests/"):
            cprint(stripped, Color.GRAY)
    proc.wait(timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"Python tests FAILED (exit code {proc.returncode}).")
    cprint("All Python tests passed.", Color.GREEN)


def _run_mca_tests() -> None:
    """Run the MCA language server test suite.

    Raises RuntimeError if any test fails.
    """
    if not shutil.which("node"):
        raise RuntimeError(
            "Node.js is not installed or not in PATH.\n"
            "Install it: https://nodejs.org/ or use your package manager:\n"
            "  sudo apt install nodejs    # Debian / Ubuntu\n"
            "  sudo pacman -S nodejs      # Arch\n"
            "  sudo dnf install nodejs    # Fedora"
        )

    test_runner = Path(__file__).resolve().parent / MCA_SERVER_TEST_DIR / "run.js"
    if not test_runner.exists():
        raise RuntimeError(f"MCA test runner not found: {test_runner}")

    cprint("Running MCA language server tests...", Color.CYAN)
    result = subprocess.run(
        ["node", str(test_runner)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    # Print test output regardless of pass/fail
    for line in result.stdout.strip().split("\n"):
        cprint(
            f"  {line}",
            Color.GRAY
            if "PASS" in line
            else (Color.RED if "FAIL" in line else Color.GRAY),
        )

    if result.returncode != 0 or "FAIL" in result.stdout:
        raise RuntimeError("MCA language server tests FAILED.")
    cprint("All MCA language server tests passed.", Color.GREEN)


def _find_vsce() -> str:
    """Locate the vsce CLI tool path."""
    # Check PATH first (works on all platforms)
    vsce_path = shutil.which("vsce")
    if vsce_path:
        return vsce_path

    # Windows: check npm global dir
    if sys.platform == "win32":
        npm_dir = Path(os.environ.get("APPDATA", "")) / "npm"
        for name in ["vsce.cmd", "vsce"]:
            p = npm_dir / name
            if p.exists():
                return str(p)

    # Fallback: npx
    for npx_name in ["npx.cmd", "npx"] if sys.platform == "win32" else ["npx"]:
        npx_path = shutil.which(npx_name)
        if npx_path:
            return f"{npx_path} --yes @vscode/vsce"

    raise RuntimeError("vsce not found. Install it: npm install -g @vscode/vsce")


def _package_vsix(extension_dir: Path) -> Path:
    """Package the VSIX extension.

    Returns the path to the generated .vsix file.
    Raises RuntimeError on failure.
    """
    vsce_cmd = _find_vsce()

    # Ensure npm dependencies are installed
    cprint("Installing npm dependencies...", Color.CYAN)
    npm_path = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm_path:
        raise RuntimeError("npm not found. Install Node.js: https://nodejs.org/")
    npm_result = subprocess.run(
        [npm_path, "install"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(extension_dir),
        check=False,
    )
    if npm_result.returncode != 0:
        raise RuntimeError(
            f"npm install failed in {extension_dir}:\n{npm_result.stderr.strip()}"
        )
    cprint("Packaging VSIX...", Color.CYAN)

    # vsce outputs the vsix to the current directory
    # posix=False on Windows keeps backslashes in the tool path intact
    result = subprocess.run(
        shlex.split(vsce_cmd, posix=(sys.platform != "win32"))
        + ["package", "--allow-missing-repository"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(extension_dir),
        check=False,
    )
    for line in result.stdout.strip().split("\n"):
        cprint(f"  {line}", Color.GRAY)

    # Parse the output to find the generated .vsix path
    vsix_name = None
    for line in result.stdout.split("\n"):
        line = line.strip()
        if line.endswith(".vsix"):
            vsix_name = line
            break

    if not vsix_name:
        if result.returncode != 0:
            raise RuntimeError(f"VSIX packaging failed:\n{result.stderr.strip()}")
        # Fallback: guess the filename from package name + version
        pkg = json.loads((extension_dir / "package.json").read_text(encoding="utf-8"))
        vsix_name = f"{pkg['name']}-{pkg['version']}.vsix"

    vsix_path = extension_dir / vsix_name
    if not vsix_path.exists():
        raise RuntimeError(f"VSIX not found at expected path: {vsix_path}")

    return vsix_path


def _verify_vsix(path: Path) -> None:
    """Verify the generated VSIX package exists and is valid."""
    if not path.exists():
        raise RuntimeError(f"VSIX package not found: {path}")

    size = path.stat().st_size
    if size == 0:
        raise RuntimeError(f"VSIX package is empty: {path}")

    cprint(f"  Size: {size / 1024:.1f} KB", Color.GRAY)


def _build_vsix_pipeline(start_time: float) -> None:
    """Full VSIX build pipeline."""
    mca_dir = Path(__file__).resolve().parent / MCA_EXTENSION_DIR

    # ── Step 1: Validate Python sources ──
    cprint("\n[1/6] Validating Python sources...", Color.CYAN)
    for rel in MCA_SPEC_SOURCES[:2]:  # only the Python implementation files
        src = Path(__file__).resolve().parent / rel
        if src.exists():
            try:
                compile(src.read_text(encoding="utf-8"), str(src), "exec")
            except SyntaxError as e:
                raise RuntimeError(f"Syntax error in {rel}: {e}")
    cprint("      Python sources OK", Color.GREEN)

    # ── Step 2: Generate MCA spec (forced) ──
    cprint("[2/6] Generating MCA language specification...", Color.CYAN)
    _generate_mca_spec(force=True)
    cprint("      Specification generated", Color.GREEN)

    # ── Step 3: Validate generated spec ──
    cprint("[3/6] Validating generated specification...", Color.CYAN)
    _validate_mca_spec()
    cprint("      Specification valid", Color.GREEN)

    # ── Step 4: Run extension tests ──
    cprint("[4/6] Running language server tests...", Color.CYAN)
    _run_mca_tests()

    # ── Step 5: Package VSIX ──
    cprint("[5/6] Packaging extension...", Color.CYAN)
    vsix_path = _package_vsix(mca_dir)
    cprint("      Extension packaged", Color.GREEN)

    # ── Step 6: Verify package ──
    cprint("[6/6] Verifying package...", Color.CYAN)
    _verify_vsix(vsix_path)
    cprint("      Package verified", Color.GREEN)

    # ── Report ──
    elapsed = time.time() - start_time
    mins, secs = divmod(elapsed, 60)
    cprint(f"\n{'=' * 50}", Color.GREEN)
    cprint(f"VSIX build completed in {int(mins):02d}:{secs:06.3f}", Color.GREEN)
    cprint(f"Output: {vsix_path}", Color.GREEN)
    cprint(f"{'=' * 50}", Color.GREEN)


# ── Command handlers ─────────────────────────────────────────────────────────


def cmd_app(args):
    start = time.time()
    BUILD_INSTALLER = getattr(args, "installer", False)
    USE_CACHE = getattr(args, "use_cache", False)
    ONLY_FILES = getattr(args, "only", None)

    IS_WINDOWS = sys.platform == "win32"
    SUFFIX = ".exe" if IS_WINDOWS else ".bin"

    SCRIPT_DIR = Path(__file__).resolve().parent
    os.chdir(SCRIPT_DIR)

    OUT_DIR = SCRIPT_DIR / "build" / "release"
    CACHE_DIR = SCRIPT_DIR / "build" / "cache"
    EXE_CACHE_DIR = CACHE_DIR / "exes"
    HASH_CACHE_DIR = CACHE_DIR / "hashes"
    PARALLEL_TEMP_DIR = SCRIPT_DIR / "build" / "temp_parallel"

    MAX_THREADS = getattr(args, "threads", None) or min(16, (os.cpu_count() or 4))
    MAX_COPY_THREADS = min(32, (os.cpu_count() or 4) * 4)

    ICON_BY_NAME = {
        "app": "tiktok2mc.ico",
        "gui": "tiktok2mc.ico",
        "start": "tiktok2mc.ico",
        "update": "tiktok2mc-update.ico",
        "update_progress": "tiktok2mc-update.ico",
        "server": "tiktok2mc-tool.ico",
        "overlay": "tiktok2mc-tool.ico",
        "test_trigger": "tiktok2mc-tool.ico",
    }
    ICONS_DIR = SCRIPT_DIR / "assets" / "icons"

    CORE_EXECUTABLES = [
        {"name": "app", "src": "src/python/main.py", "dest": "core"},
        {"name": "gui", "src": "src/python/gui.py", "dest": "core", "windowed": True},
        {"name": "update", "src": "src/python/update.py", "dest": ""},
        {"name": "server", "src": "src/python/server.py", "dest": "core"},
        {"name": "overlay", "src": "src/python/overlay.py", "dest": "core"},
        {"name": "start", "src": "src/python/start.py", "dest": ""},
        {
            "name": "update_progress",
            "src": "src/python/update_progress.py",
            "dest": "core",
            "windowed": True,
        },
        {"name": "test_trigger", "src": "src/python/send_trigger.py", "dest": "test"},
    ]

    try:
        # ----- Preparation & Directory Structure -----
        cprint("Preparing build environment...", Color.CYAN)

        if OUT_DIR.exists() and not ONLY_FILES:
            shutil.rmtree(OUT_DIR)

        REQUIRED_DIRS = [
            EXE_CACHE_DIR,
            HASH_CACHE_DIR,
            OUT_DIR,
            PARALLEL_TEMP_DIR,
            OUT_DIR / "core",
            OUT_DIR / "plugins",
            OUT_DIR / "core" / "runtime",
            OUT_DIR / "core" / "lib",
            OUT_DIR / "core" / "templates",
            OUT_DIR / "core" / "static" / "css",
            OUT_DIR / "server" / "java",
            OUT_DIR / "server" / "default",
            OUT_DIR / "versions" / "1.21.11",
            OUT_DIR / "config",
            OUT_DIR / "data",
            OUT_DIR / "test",
            OUT_DIR / "logs",
            OUT_DIR / "server" / "default" / "plugins" / "MinecraftServerAPI",
            OUT_DIR / "server" / "plugins_source" / "MinecraftServerAPI",
            OUT_DIR
            / "server"
            / "datapack"
            / "StreamingTool"
            / "data"
            / "streamingtool"
            / "function",
            OUT_DIR / "server" / "default" / "plugins" / "DelayedTNT",
            OUT_DIR / "server" / "plugins_source" / "DelayedTNT",
            OUT_DIR / "hooks",
            OUT_DIR / "docs",
        ]

        for d in REQUIRED_DIRS:
            d.mkdir(parents=True, exist_ok=True)

        if PARALLEL_TEMP_DIR.exists():
            shutil.rmtree(PARALLEL_TEMP_DIR, ignore_errors=True)
        PARALLEL_TEMP_DIR.mkdir(parents=True, exist_ok=True)

        # ----- Collect Build Tasks -----
        cprint("Collecting all files to compile...", Color.CYAN)
        all_build_tasks = []

        for item in CORE_EXECUTABLES:
            suffix = item.get("suffix", SUFFIX)
            task = {
                "name": item["name"] + suffix,
                "src": item["src"],
                "dest": item["dest"],
            }
            if item.get("windowed"):
                task["windowed"] = True
            icon_file = ICON_BY_NAME.get(item["name"])
            if icon_file:
                task["icon"] = icon_file
            all_build_tasks.append(task)

        src_plugins_root = SCRIPT_DIR / "src" / "plugins"
        plugin_hook_dirs: list[Path] = []
        if src_plugins_root.exists():
            for py_file in src_plugins_root.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                if (
                    py_file.parent.name in ("test", "example_plugin")
                    and py_file.parent.parent.name == "plugins"
                ):
                    continue
                if "hooks" in py_file.parent.parts:
                    plugin_hook_dirs.append(py_file.parent)
                    continue
                rel = py_file.parent.relative_to(src_plugins_root)
                dest = str(Path("plugins") / rel) if str(rel) != "." else "plugins"
                all_build_tasks.append(
                    {
                        "name": f"{py_file.stem}{SUFFIX}",
                        "src": str(py_file),
                        "dest": dest,
                    }
                )

                for extra_file in [
                    "plugin.json",
                    "version.txt",
                    "README.md",
                    "config.yaml",
                ]:
                    extra_path = py_file.parent / extra_file
                    if extra_path.exists():
                        target_dir = OUT_DIR / dest
                        target_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(extra_path, target_dir / extra_file)

        if ONLY_FILES:
            available_names = sorted({t["name"] for t in all_build_tasks})
            all_build_tasks, matched_names, unmatched = _filter_build_tasks(
                all_build_tasks, ONLY_FILES
            )
            if unmatched:
                raise RuntimeError(
                    f"No build task matches: {', '.join(unmatched)}.\n"
                    f"Available tasks: {', '.join(available_names)}"
                )
            cprint(
                f"Selective build: {len(all_build_tasks)} file(s) -> {', '.join(matched_names)}",
                Color.CYAN,
            )

        # ----- Execution: Parallel Build -----
        cprint(
            f"\nStarting parallel build with {MAX_THREADS} threads for {len(all_build_tasks)} files...",
            Color.CYAN,
        )

        def sha256_file(filepath):
            h = hashlib.sha256()
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()

        def _resolve_module(module: str, src_root: Path) -> str | None:
            rel = module.replace(".", "/")
            for candidate in [f"{rel}.py", f"{rel}/__init__.py"]:
                path = src_root / candidate
                if path.exists():
                    return str(path.relative_to(SCRIPT_DIR))
            return None

        def _parent_inits(module: str) -> list[str]:
            result: list[str] = []
            parts = module.replace(".", "/").split("/")
            for i in range(1, len(parts)):
                init = SCRIPT_DIR / "src" / "/".join(parts[:i]) / "__init__.py"
                if init.exists():
                    result.append(str(init.relative_to(SCRIPT_DIR)))
            return result

        def _try_resolve_local(
            module: str, src_root: Path, source_path: Path
        ) -> list[str]:
            resolved: list[str] = []
            if module.startswith("."):
                parts = module.split(".")
                dots = len(parts[0])
                rel_parts = parts[1:] if len(parts) > 1 else []
                try:
                    src_rel = source_path.resolve().relative_to(SCRIPT_DIR)
                except ValueError:
                    return resolved
                pkg_parts = list(src_rel.parent.parts)
                for _ in range(dots - 1):
                    if pkg_parts:
                        pkg_parts.pop()
                if not pkg_parts:
                    return resolved
                base = SCRIPT_DIR / Path(*pkg_parts)
                if rel_parts:
                    sub = "/".join(rel_parts)
                    for candidate in [f"{sub}.py", f"{sub}/__init__.py"]:
                        p = base / candidate
                        if p.exists():
                            resolved.append(str(p.relative_to(SCRIPT_DIR)))
                else:
                    init = base / "__init__.py"
                    if init.exists():
                        resolved.append(str(init.relative_to(SCRIPT_DIR)))
                return resolved
            path = _resolve_module(module, src_root)
            if path:
                resolved.append(path)
                resolved.extend(_parent_inits(module))
            return resolved

        def resolve_transitive_imports(source_path: Path) -> set[str]:
            src_root = SCRIPT_DIR / "src"
            if not src_root.exists():
                return set()
            visited: set[str] = set()
            queue: list[Path] = [source_path.resolve()]
            while queue:
                path = queue.pop()
                try:
                    rel = str(path.resolve().relative_to(SCRIPT_DIR))
                except ValueError:
                    continue
                if rel in visited:
                    continue
                visited.add(rel)
                try:
                    with open(path, "rb") as f:
                        tree = ast.parse(f.read())
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            for r in _try_resolve_local(alias.name, src_root, path):
                                if r not in visited:
                                    queue.append(SCRIPT_DIR / r)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            for r in _try_resolve_local(node.module, src_root, path):
                                if r not in visited:
                                    queue.append(SCRIPT_DIR / r)
                        if node.level:
                            dots = "." * node.level
                            mod = dots + (node.module or "")
                            for r in _try_resolve_local(mod, src_root, path):
                                if r not in visited:
                                    queue.append(SCRIPT_DIR / r)
            return visited

        def _imports_module(path: Path, module: str) -> bool:
            """Return True if a source file statically imports ``module``.

            PyQt6 / PyQt6-WebEngine are only bundled into binaries that
            actually use webview, so ``--collect-all=PyQt6`` stays limited
            to gui/overlay/plugins instead of inflating every binary.
            """
            try:
                with open(path, "rb") as f:
                    tree = ast.parse(f.read())
            except (OSError, SyntaxError):
                return False
            prefix = module + "."
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    if any(
                        a.name == module or a.name.startswith(prefix)
                        for a in node.names
                    ):
                        return True
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and (node.module == module or node.module.startswith(prefix))
                ):
                    return True
            return False

        def _needs_qt(source: Path, deps: set[str]) -> bool:
            """Whether a binary pulls in Qt (webview/PyQt6) directly or via deps."""
            if _imports_module(source, "webview") or _imports_module(source, "PyQt6"):
                return True
            for dep in sorted(deps):
                if _imports_module(SCRIPT_DIR / dep, "webview") or _imports_module(
                    SCRIPT_DIR / dep, "PyQt6"
                ):
                    return True
            return False

        QT_BUNDLE_CACHE = CACHE_DIR / "qt_bundle"

        def _qt_bundle_hash(qt_tasks: list[dict]) -> str:
            """Combined hash over all Qt entry points, their deps, and build.py."""
            h = hashlib.sha256()
            for task in sorted(qt_tasks, key=lambda t: t["name"]):
                src = Path(task["src"]).resolve()
                h.update(src.read_bytes())
                for dep in sorted(resolve_transitive_imports(src)):
                    h.update(dep.encode())
                    dep_path = SCRIPT_DIR / dep
                    if dep_path.exists():
                        h.update(sha256_file(dep_path).encode())
            build_py = SCRIPT_DIR / "build.py"
            if build_py.exists():
                h.update(sha256_file(build_py).encode())
            return h.hexdigest()

        def _bundle_exe_name(task: dict) -> str:
            """Unique PyInstaller EXE name for a task (plugins are all ``main.py``)."""
            src = Path(task["src"]).resolve()
            return (
                str(src.relative_to(SCRIPT_DIR)).replace(os.sep, "_").replace(".py", "")
            )

        def _write_qt_spec(spec_path: Path, qt_tasks: list[dict]) -> None:
            """Write a shared-COLLECT onedir spec so all Qt binaries share one _internal."""
            lines = [
                "# -*- mode: python ; coding: utf-8 -*-",
                "from PyInstaller.utils.hooks import collect_all",
                "",
                f"QT_SRC = {str((SCRIPT_DIR / 'src').resolve())!r}",
                "qt_datas, qt_binaries, qt_hidden = collect_all('PyQt6')",
                "",
            ]
            names: list[str] = []
            for task in qt_tasks:
                exe_name = _bundle_exe_name(task)
                names.append(exe_name)
                src_file = str((SCRIPT_DIR / task["src"]).resolve())
                console = not task.get("windowed")
                lines += [
                    f"{exe_name}_a = Analysis(",
                    f"    [{src_file!r}],",
                    "    pathex=[QT_SRC],",
                    "    binaries=qt_binaries,",
                    "    datas=qt_datas,",
                    "    hiddenimports=['_multiprocessing'] + qt_hidden,",
                    "    excludes=[],",
                    "    noarchive=False,",
                    ")",
                    f"{exe_name}_pyz = PYZ({exe_name}_a.pure, {exe_name}_a.zipped_data)",
                    f"{exe_name}_exe = EXE(",
                    f"    {exe_name}_pyz,",
                    f"    {exe_name}_a.scripts,",
                    "    [],",
                    "    exclude_binaries=True,",
                    f"    name={exe_name!r},",
                    f"    console={console!s},",
                    "    debug=False,",
                    "    bootloader_ignore_signals=False,",
                    "    strip=False,",
                    "    upx=False,",
                    "    runtime_tmpdir=None,",
                    ")",
                    "",
                ]
            collect_args: list[str] = []
            for name in names:
                collect_args += [
                    f"{name}_exe",
                    f"{name}_a.binaries",
                    f"{name}_a.zipfiles",
                    f"{name}_a.datas",
                ]
            lines += ["coll = COLLECT("]
            lines += [f"    {a}," for a in collect_args]
            lines += [
                "    strip=False,",
                "    upx=False,",
                "    upx_exclude=[],",
                "    name='tiktok2mc-qt',",
                ")",
                "",
            ]
            spec_path.write_text("\n".join(lines), encoding="utf-8")

        def _make_symlink(target: str, link: Path) -> None:
            if link.is_symlink() or link.exists():
                try:
                    link.unlink()
                except OSError:
                    pass
            try:
                os.symlink(target, link)
            except OSError as e:
                cprint(
                    f"WARNING: could not create symlink {link} -> {target}: {e}",
                    Color.YELLOW,
                )

        def _deploy_qt_bundle(cache_dir: Path, qt_tasks: list[dict]) -> None:
            internal_src = cache_dir / "_internal"
            internal_dst = OUT_DIR / "core" / "runtime" / "_internal"
            internal_dst.parent.mkdir(parents=True, exist_ok=True)
            if internal_dst.exists():
                shutil.rmtree(internal_dst, ignore_errors=True)
            shutil.copytree(internal_src, internal_dst, symlinks=True)

            for task in qt_tasks:
                exe_name = _bundle_exe_name(task)
                src_exe = cache_dir / exe_name
                target_dir = OUT_DIR if not task["dest"] else OUT_DIR / task["dest"]
                target_dir.mkdir(parents=True, exist_ok=True)
                final_path = target_dir / task["name"]
                shutil.copy2(src_exe, final_path)
                os.chmod(final_path, 0o755)
                cprint(f"Done: {task['name']} (shared runtime)", Color.GREEN)

            # Relative _internal symlink in every directory holding a Qt binary.
            for task in qt_tasks:
                if not task["dest"]:
                    continue
                depth = len(Path(task["dest"]).parts)
                rel_up = "/".join([".."] * depth)
                link_dir = OUT_DIR / task["dest"]
                link_dir.mkdir(parents=True, exist_ok=True)
                _make_symlink(
                    f"{rel_up}/core/runtime/_internal", link_dir / "_internal"
                )

            # Root-level _internal symlink for --onefile binaries (start, update).
            # PyInstaller 6.x on Linux resolves libpython relative to the
            # executable directory, so onefile binaries in the release root need
            # the same _internal/ directory that the Qt onedir binaries use.
            _make_symlink("core/runtime/_internal", OUT_DIR / "_internal")

            # Onefile binaries that live in core/ (server.bin, gui.bin, ...)
            # resolve _internal/ relative to their own directory, so core/ needs
            # the same symlink that the release root gets.
            _make_symlink("runtime/_internal", OUT_DIR / "core" / "_internal")

        def _build_linux_qt_bundle(qt_tasks: list[dict]) -> bool:
            """Build all Qt binaries as one onedir bundle sharing a single PyQt6 runtime."""
            if IS_WINDOWS or not qt_tasks:
                return True

            bundle_hash = _qt_bundle_hash(qt_tasks)
            cache_dir = QT_BUNDLE_CACHE / bundle_hash
            stamp = QT_BUNDLE_CACHE / "current.txt"
            cached = (
                cache_dir.exists()
                and stamp.exists()
                and stamp.read_text().strip() == bundle_hash
            )

            if USE_CACHE:
                if not cached:
                    cprint(
                        "  MISSING: qt-bundle — cache entry does not exist", Color.RED
                    )
                    cache_missing.append("qt-bundle")
                    return False
                cprint("Cache hit: qt-bundle (use-cache)", Color.GRAY)
                _deploy_qt_bundle(cache_dir, qt_tasks)
                return True

            if cached:
                cprint("Cache hit: qt-bundle", Color.GRAY)
                _deploy_qt_bundle(cache_dir, qt_tasks)
                return True

            cprint(
                f"[Linux] Building shared PyQt6 runtime for {len(qt_tasks)} binaries...",
                Color.YELLOW,
            )
            unique_id = uuid.uuid4().hex[:8]
            t_dist = PARALLEL_TEMP_DIR / f"qtdist_{unique_id}"
            t_work = PARALLEL_TEMP_DIR / f"qtwork_{unique_id}"
            t_spec = PARALLEL_TEMP_DIR / f"qtspec_{unique_id}"
            log_file = PARALLEL_TEMP_DIR / f"qtlog_{unique_id}.txt"
            for d in (t_dist, t_work, t_spec):
                d.mkdir(parents=True, exist_ok=True)
            spec_path = t_spec / "tiktok2mc_qt.spec"
            _write_qt_spec(spec_path, qt_tasks)

            cmd = [
                sys.executable,
                "-m",
                "PyInstaller",
                str(spec_path),
                "--distpath",
                str(t_dist),
                "--workpath",
                str(t_work),
                "--noconfirm",
                "--log-level",
                "ERROR",
            ]
            try:
                with open(log_file, "w", encoding="utf-8") as lf:
                    proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
                    try:
                        return_code = proc.wait(timeout=1800)
                    except subprocess.TimeoutExpired:
                        _kill_proc_tree(proc.pid)
                        cprint("TIMEOUT: qt-bundle after 1800s", Color.RED)
                        if log_file.exists():
                            cprint(log_file.read_text(errors="replace"), Color.RED)
                        return False
            except Exception as e:
                cprint(f"ERROR running PyInstaller for qt-bundle: {e}", Color.RED)
                return False

            bundle_root = t_dist / "tiktok2mc-qt"
            if return_code != 0 or not bundle_root.exists():
                cprint(f"FAILED: qt-bundle (exit code {return_code})", Color.RED)
                if log_file.exists():
                    cprint(log_file.read_text(errors="replace"), Color.RED)
                return False

            QT_BUNDLE_CACHE.mkdir(parents=True, exist_ok=True)
            if cache_dir.exists():
                shutil.rmtree(cache_dir, ignore_errors=True)
            shutil.move(str(bundle_root), str(cache_dir))
            stamp.write_text(bundle_hash)

            for p in (t_dist, t_work, t_spec):
                shutil.rmtree(p, ignore_errors=True)
            if log_file.exists():
                log_file.unlink(missing_ok=True)

            _deploy_qt_bundle(cache_dir, qt_tasks)
            return True

        def build_one(item):
            full_src = Path(item["src"]).resolve()
            safe_name = str(full_src.relative_to(SCRIPT_DIR)).replace(os.sep, "_")
            hash_file = HASH_CACHE_DIR / f"{safe_name}.sha256"
            dep_hash_file = HASH_CACHE_DIR / f"{safe_name}.dep_sha256"
            cache_exe = EXE_CACHE_DIR / safe_name.replace(".py", SUFFIX)

            current_hash = sha256_file(full_src)

            deps = resolve_transitive_imports(full_src)
            needs_qt = _needs_qt(full_src, deps)
            build_py = SCRIPT_DIR / "build.py"

            dep_hasher = hashlib.sha256()
            dep_hasher.update(current_hash.encode())
            for dep in sorted(deps):
                dep_hasher.update(dep.encode())
                dep_path = SCRIPT_DIR / dep
                if dep_path.exists():
                    dep_hasher.update(sha256_file(dep_path).encode())
                else:
                    dep_hasher.update(b"")
            if build_py.exists():
                dep_hasher.update(sha256_file(build_py).encode())
            icon_file = item.get("icon")
            if icon_file:
                icon_path = ICONS_DIR / icon_file
                if icon_path.exists():
                    dep_hasher.update(sha256_file(icon_path).encode())
            combined_hash = dep_hasher.hexdigest()

            target_dir = OUT_DIR if not item["dest"] else OUT_DIR / item["dest"]
            target_dir.mkdir(parents=True, exist_ok=True)
            final_path = target_dir / item["name"]

            # --use-cache: only copy from cache, never build
            if USE_CACHE:
                if not cache_exe.exists():
                    cprint(
                        f"  MISSING: {item['name']} — cache entry does not exist",
                        Color.RED,
                    )
                    cache_missing.append(item["name"])
                    return False

                cached_hash = (
                    hash_file.read_text().strip() if hash_file.exists() else ""
                )
                cached_dep_hash = (
                    dep_hash_file.read_text().strip() if dep_hash_file.exists() else ""
                )

                if cached_hash != current_hash or cached_dep_hash != combined_hash:
                    cprint(
                        f"  OUTDATED: {item['name']} — source changed since last build",
                        Color.YELLOW,
                    )
                    cache_outdated.append(item["name"])

                cprint(f"Cache hit: {item['name']} (use-cache)", Color.GRAY)
                shutil.copy2(cache_exe, final_path)
                return True

            # Normal build: check cache first
            need_build = True
            if (
                hash_file.exists()
                and dep_hash_file.exists()
                and cache_exe.exists()
                and hash_file.read_text().strip() == current_hash
                and dep_hash_file.read_text().strip() == combined_hash
            ):
                need_build = False

            target_dir = OUT_DIR if not item["dest"] else OUT_DIR / item["dest"]
            target_dir.mkdir(parents=True, exist_ok=True)
            final_path = target_dir / item["name"]

            if need_build:
                if not shutil.which(sys.executable):
                    raise RuntimeError(
                        "Python interpreter not found.\n"
                        "Ensure Python 3.12+ is installed and in PATH."
                    )
                try:
                    import importlib.util

                    if importlib.util.find_spec("PyInstaller") is None:
                        raise ImportError
                except ImportError:
                    raise RuntimeError(
                        "PyInstaller is not installed.\n"
                        "Install it: pip install pyinstaller"
                    )

                cprint(f"[Parallel] Compiling: {item['name']}...", Color.YELLOW)

                unique_id = uuid.uuid4().hex[:8]
                t_dist = PARALLEL_TEMP_DIR / f"dist_{unique_id}"
                t_work = PARALLEL_TEMP_DIR / f"work_{unique_id}"
                t_spec = PARALLEL_TEMP_DIR / f"spec_{unique_id}"
                log_file = PARALLEL_TEMP_DIR / f"log_{unique_id}.txt"

                pyinstaller_name = (
                    item["name"] if not IS_WINDOWS else item["name"].replace(SUFFIX, "")
                )
                cmd = [
                    sys.executable,
                    "-m",
                    "PyInstaller",
                    "--onefile",
                    "--path=src",
                    str(full_src),
                    "--name",
                    pyinstaller_name,
                    "--distpath",
                    str(t_dist),
                    "--workpath",
                    str(t_work),
                    "--specpath",
                    str(t_spec),
                    "--noconfirm",
                    "--log-level",
                    "ERROR",
                    "--hidden-import=_multiprocessing",
                ]
                if not IS_WINDOWS and needs_qt:
                    cmd += [
                        "--collect-all=PyQt6",
                        "--collect-binaries=PyQt6",
                        "--collect-data=PyQt6",
                    ]
                if IS_WINDOWS:
                    # pywebview uses Qt only on Linux (gui.py forces gui="qt"
                    # there). On Windows the native EdgeChromium/WebView2
                    # backend runs, so bundling the installed PyQt6/QtWebEngine
                    # (~180 MB) into every webview-importing binary is dead
                    # weight — exclude all Qt bindings.
                    for qt_binding in ("PyQt6", "PyQt5", "PySide6", "PySide2"):
                        cmd += ["--exclude-module", qt_binding]
                if item.get("windowed"):
                    cmd.append("--noconsole")
                icon_file = item.get("icon")
                if IS_WINDOWS and icon_file:
                    icon_path = ICONS_DIR / icon_file
                    if icon_path.exists():
                        cmd += ["--icon", str(icon_path)]

                try:
                    with open(log_file, "w", encoding="utf-8") as lf:
                        proc = subprocess.Popen(
                            cmd, stdout=lf, stderr=subprocess.STDOUT
                        )
                        try:
                            return_code = proc.wait(timeout=600)
                        except subprocess.TimeoutExpired:
                            _kill_proc_tree(proc.pid)
                            cprint(f"TIMEOUT: {item['name']} after 600s", Color.RED)
                            if log_file.exists():
                                cprint(log_file.read_text(errors="replace"), Color.RED)
                            return False
                except Exception as e:
                    cprint(
                        f"ERROR running PyInstaller for {item['name']}: {e}", Color.RED
                    )
                    return False

                if return_code != 0:
                    cprint(
                        f"FAILED: {item['name']} (exit code {return_code})", Color.RED
                    )
                    if log_file.exists():
                        cprint(log_file.read_text(errors="replace"), Color.RED)
                    return False

                fresh = t_dist / (pyinstaller_name + (".exe" if IS_WINDOWS else ""))
                if fresh.exists():
                    shutil.copy2(fresh, final_path)
                    shutil.copy2(fresh, cache_exe)
                    hash_file.write_text(current_hash)
                    dep_hash_file.write_text(combined_hash)
                    cprint(f"Done: {item['name']}", Color.GREEN)
                else:
                    cprint(f"FAILED: {item['name']}", Color.RED)
                    if log_file.exists():
                        cprint(log_file.read_text(errors="replace"), Color.RED)
                    return False

                for p in (t_dist, t_work, t_spec):
                    shutil.rmtree(p, ignore_errors=True)
                if log_file.exists():
                    log_file.unlink(missing_ok=True)
            else:
                cprint(f"Cache hit: {item['name']}", Color.GRAY)
                if not final_path.exists():
                    shutil.copy2(cache_exe, final_path)

            return True

        cache_missing: list[str] = []
        cache_outdated: list[str] = []

        # ----- Linux: shared PyQt6 runtime bundle -----
        # Qt binaries (gui, overlay, plugins) are built together as one onedir
        # bundle so they share a single PyQt6/QtWebEngine _internal instead of
        # each embedding a full WebEngine copy. Everything else stays onefile.
        qt_tasks: list[dict] = []
        plain_tasks: list[dict] = []
        if not IS_WINDOWS:
            for task in all_build_tasks:
                src = Path(task["src"]).resolve()
                if _needs_qt(src, resolve_transitive_imports(src)):
                    qt_tasks.append(task)
                else:
                    plain_tasks.append(task)
            if qt_tasks and not _build_linux_qt_bundle(qt_tasks):
                raise RuntimeError("Linux shared PyQt6 runtime build failed.")
        else:
            plain_tasks = list(all_build_tasks)

        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            futures = {executor.submit(build_one, task): task for task in plain_tasks}
            failed = False
            for future in as_completed(futures):
                task = futures[future]
                try:
                    if not future.result():
                        failed = True
                except Exception as exc:
                    cprint(f"FAILED: {task['name']} - {exc}", Color.RED)
                    failed = True
            if failed:
                raise RuntimeError("One or more build tasks failed.")

        if USE_CACHE:
            cprint("\n--- Cache Summary ---", Color.CYAN)
            total = len(all_build_tasks)
            ok = total - len(cache_missing)
            cprint(
                f"  Total: {total}  |  From cache: {ok}  |  Missing: {len(cache_missing)}  |  Outdated: {len(cache_outdated)}",
                Color.CYAN,
            )
            if cache_missing:
                cprint("\n  Missing executables (not in cache):", Color.RED)
                for name in cache_missing:
                    cprint(f"    - {name}", Color.RED)
                cprint("\n  Run a full build first:  python build.py app", Color.YELLOW)
            if cache_outdated:
                cprint(
                    "\n  Outdated executables (source changed since last build):",
                    Color.YELLOW,
                )
                for name in cache_outdated:
                    cprint(f"    - {name}", Color.YELLOW)

        # ----- Assets & Resources -----
        cprint(
            f"\nSynchronizing assets and resources with {MAX_COPY_THREADS} threads...",
            Color.CYAN,
        )

        def sync_folder(source, destination, threads=MAX_COPY_THREADS, exclude=None):
            src = Path(source)
            dst = Path(destination)
            if not src.exists():
                return
            dst.mkdir(parents=True, exist_ok=True)
            exclude = exclude or []

            def is_excluded(path):
                rel = path.relative_to(src)
                for pattern in exclude:
                    if pattern.endswith("/**"):
                        base = Path(pattern[:-3])
                        if base in rel.parents or rel == base:
                            return True
                    elif fnmatch.fnmatch(str(rel), pattern):
                        return True
                return False

            all_files = [
                f for f in src.rglob("*") if f.is_file() and not is_excluded(f)
            ]

            def copy_one(f):
                rel = f.relative_to(src)
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)

            with ThreadPoolExecutor(max_workers=threads) as pool:
                pool.map(copy_one, all_files)

        sync_folder("assets", OUT_DIR / "core" / "assets")
        sync_folder("templates", OUT_DIR / "core" / "templates")
        sync_folder("tools/Java", OUT_DIR / "server" / "java")
        sync_folder("src/hooks", OUT_DIR / "hooks", exclude=["example_hook/**"])
        for hook_src_dir in set(plugin_hook_dirs):
            rel_hook = hook_src_dir.relative_to(SCRIPT_DIR / "src")
            sync_folder(hook_src_dir, OUT_DIR / rel_hook)
        sync_folder("docs", OUT_DIR / "docs", exclude=["public/**", ".gitignore"])

        FILES = [
            ("defaults/config.yaml", "config/config.yaml"),
            ("defaults/gifts.json", "core/gifts.json"),
            ("defaults/comment_commands.yaml", "data/comment_commands.yaml"),
            ("LICENSE", "LICENSE"),
            ("README.md", "README.md"),
            ("defaults/actions.mca", "data/actions.mca"),
            (
                "defaults/configServerAPI.yml",
                "server/default/plugins/MinecraftServerAPI/config.yml",
            ),
            (
                "defaults/configServerAPI.yml",
                "server/plugins_source/MinecraftServerAPI/config.yml",
            ),
            (
                "defaults/DelayedTNTconfig.yml",
                "server/default/plugins/DelayedTNT/config.yml",
            ),
            (
                "defaults/DelayedTNTconfig.yml",
                "server/plugins_source/DelayedTNT/config.yml",
            ),
            (
                "tools/MinecraftServerAPI-1.21.x.jar",
                "server/default/plugins/MinecraftServerAPI-1.21.x.jar",
            ),
            (
                "tools/MinecraftServerAPI-1.21.x.jar",
                "server/plugins_source/MinecraftServerAPI-1.21.x.jar",
            ),
            ("tools/DelayedTNT.jar", "server/default/plugins/DelayedTNT.jar"),
            ("tools/DelayedTNT.jar", "server/plugins_source/DelayedTNT.jar"),
            ("tools/server.jar", "server/default/server.jar"),
            ("tools/server.jar", "versions/1.21.11/server.jar"),
            ("tools/mca.vsix", "core/assets/mca.vsix"),
            ("AIPrompt.md", "AIPrompt.md"),
        ]

        for src_rel, dst_rel in FILES:
            src_path = Path(src_rel)
            if src_path.exists():
                target = OUT_DIR / dst_rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, target)

        config_src = OUT_DIR / "config" / "config.yaml"
        config_default = OUT_DIR / "config" / "config.default.yaml"
        if config_src.exists():
            header = (
                "# -------------------------------------------------------------------------\n"
                "# STREAMING TOOL CONFIGURATION TEMPLATE\n"
                "# -------------------------------------------------------------------------\n"
                "# This file is a template.\n"
                "# Personal settings should be changed in 'config.yaml' only.\n"
                "# -------------------------------------------------------------------------\n"
            )
            content = config_src.read_text(encoding="utf-8")
            config_default.write_text(header + content, encoding="utf-8")

        (OUT_DIR / "data" / "diagnostics").mkdir(parents=True, exist_ok=True)

        # ----- Metadata & Cleanup -----
        cprint("Cleaning up temporary files...", Color.CYAN)
        (OUT_DIR / "version.txt").write_text(
            f"ToolVersion: {TOOL_VERSION}\nUpdaterVersion: {UPDATER_VERSION}\n",
            encoding="utf-8",
        )

        if PARALLEL_TEMP_DIR.exists():
            shutil.rmtree(PARALLEL_TEMP_DIR, ignore_errors=True)

        for cache_dir in sorted(SCRIPT_DIR.rglob("__pycache__")):
            shutil.rmtree(cache_dir, ignore_errors=True)

        # ----- Release / Upload Script -----
        cprint("Creating upload.py...", Color.CYAN)
        upload_content = (
            "#!/usr/bin/env python3\n"
            "import subprocess\n"
            "import sys\n"
            "import os\n"
            "from pathlib import Path\n"
            "import logging\n"
            "\n"
            "logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)\n"
            "log = logging.getLogger(__name__)\n"
            "\n"
            '_src = Path(__file__).resolve().parent / "src"\n'
            "if str(_src) not in sys.path:\n"
            "    sys.path.insert(0, str(_src))\n"
            "\n"
            "from core.version import TOOL_VERSION\n"
            "\n"
            "os.chdir(Path(__file__).resolve().parent)\n"
            "\n"
            'C = "\\033[96m"\n'
            'G = "\\033[92m"\n'
            'Y = "\\033[93m"\n'
            'R = "\\033[91m"\n'
            'X = "\\033[0m"\n'
            "\n"
            "def run(cmd, check=True):\n"
            "    log.info(f\"{C}> {' '.join(cmd)}{X}\")\n"
            "    return subprocess.run(cmd, check=check, capture_output=False)\n"
            "\n"
            "# 1. Stage all changes\n"
            'log.info(f"\\n{C}Staging changes...{X}")\n'
            'run(["git", "add", "-A"])\n'
            "\n"
            "# 2. Commit (ask for message)\n"
            f"msg = input(f\"\\n{{Y}}Commit message (Enter = 'Release {TOOL_VERSION}'): {{X}}\").strip()\n"
            "if not msg:\n"
            f'    msg = "Release {TOOL_VERSION}"\n'
            'result = run(["git", "commit", "-m", msg], check=False)\n'
            "if result.returncode != 0:\n"
            '    log.info(f"{Y}No changes to commit, continuing...{X}")\n'
            "\n"
            "# 3. Push\n"
            'log.info(f"\\n{C}Pushing to remote...{X}")\n'
            'run(["git", "push"])\n'
            "\n"
            "# 4. Create and push tag\n"
            f'log.info(f"\\n{{C}}Creating tag {TOOL_VERSION}...{{X}}")\n'
            f'run(["git", "tag", "-d", "{TOOL_VERSION}"], check=False)\n'
            f'run(["git", "push", "origin", "--delete", "{TOOL_VERSION}"], check=False)\n'
            f'run(["git", "tag", "{TOOL_VERSION}"])\n'
            f'run(["git", "push", "origin", "{TOOL_VERSION}"])\n'
            "\n"
            f'log.info(f"\\n{{G}}Done! GitHub Actions will now build & release {TOOL_VERSION}{{X}}")\n'
            'log.info(f"{C}   Check progress: https://github.com/<OWNER>/<REPO>/actions{X}")\n'
            "\n"
            'input("\\nPress Enter to exit...")\n'
        )
        Path("upload.py").write_text(upload_content, encoding="utf-8")

        # ----- GUI Installer -----
        if BUILD_INSTALLER and IS_WINDOWS:
            cprint("Building GUI installer...", Color.CYAN)
            import subprocess as _sp

            nsis_script = SCRIPT_DIR / "installer" / "install.nsi"
            installer_out = SCRIPT_DIR / "build" / "TikTok2MC-Setup.exe"
            if nsis_script.exists():
                makensis_cmd = shutil.which("makensis")
                if not makensis_cmd:
                    for nsis_path in [
                        Path("C:/Program Files (x86)/NSIS/Bin/makensis.exe"),
                        Path("C:/Program Files/NSIS/Bin/makensis.exe"),
                        Path(os.environ.get("LOCALAPPDATA", ""))
                        / "NSIS"
                        / "Bin"
                        / "makensis.exe",
                    ]:
                        if nsis_path.exists():
                            makensis_cmd = str(nsis_path)
                            break

                if not makensis_cmd:
                    cprint(
                        "makensis not found — install NSIS or restart your terminal",
                        Color.YELLOW,
                    )

                if makensis_cmd:
                    try:
                        _sp.run(
                            [
                                makensis_cmd,
                                f"-DPRODUCT_VERSION={TOOL_VERSION}",
                                f"-DOUT_FILE={installer_out}",
                                str(nsis_script),
                            ],
                            check=True,
                            capture_output=True,
                        )
                        cprint(f"Installer created: {installer_out}", Color.GREEN)
                        installer_in_release = OUT_DIR / installer_out.name
                        shutil.copy2(installer_out, installer_in_release)
                        cprint(
                            f"Installer copied to release: {installer_in_release}",
                            Color.GREEN,
                        )
                    except _sp.CalledProcessError as e:
                        cprint(
                            f"Installer build failed: {e.stderr.decode(errors='replace')}",
                            Color.RED,
                        )
            else:
                cprint(f"NSIS script not found at {nsis_script}", Color.YELLOW)

        elif BUILD_INSTALLER and not IS_WINDOWS:
            cprint("Building Linux shell installer...", Color.CYAN)
            linux_template = SCRIPT_DIR / "installer" / "install_linux.sh"
            if linux_template.exists():
                import tarfile

                installer_out = SCRIPT_DIR / "build" / "TikTok2Mc-Linux-Setup.sh"
                tar_path = SCRIPT_DIR / "build" / "TikTok2Mc-Linux.tar.gz"

                with tarfile.open(tar_path, "w:gz") as tf:
                    for entry in OUT_DIR.rglob("*"):
                        if entry.is_file() or entry.is_symlink():
                            tf.add(entry, arcname=entry.relative_to(OUT_DIR))

                marker = b"__ARCHIVE_BELOW__"
                template_data = linux_template.read_bytes().rstrip(b"\r\n")
                if template_data.endswith(marker):
                    template_data = template_data[: -len(marker)].rstrip(b"\r\n")

                with open(installer_out, "wb") as outf:
                    outf.write(template_data)
                    outf.write(b"\n" + marker + b"\n")
                    with open(tar_path, "rb") as tgf:
                        outf.write(tgf.read())

                os.chmod(installer_out, 0o755)
                cprint(f"Linux installer created: {installer_out}", Color.GREEN)

                installer_in_release = OUT_DIR / installer_out.name
                shutil.copy2(installer_out, installer_in_release)
                cprint(
                    f"Installer copied to release: {installer_in_release}", Color.GREEN
                )
            else:
                cprint(
                    f"Linux installer template not found at {linux_template}",
                    Color.YELLOW,
                )

        # --- Finish ---
        elapsed = time.time() - start
        minutes, seconds = divmod(elapsed, 60)
        cprint("\n======================================", Color.GREEN)
        cprint(f"Build completed in {int(minutes):02d}:{seconds:06.3f}", Color.GREEN)
        cprint("======================================", Color.GREEN)

    except Exception as e:
        elapsed = time.time() - start
        minutes, seconds = divmod(elapsed, 60)
        cprint("\n======================================", Color.RED)
        cprint(f"Build FAILED in {int(minutes):02d}:{seconds:06.3f}", Color.RED)
        cprint("======================================", Color.RED)
        cprint("\nError message:", Color.YELLOW)
        cprint(str(e), Color.RED)
        cprint("======================================", Color.RED)
        sys.exit(1)


def cmd_vsix(_args):
    start = time.time()
    try:
        _build_vsix_pipeline(start)
    except Exception as e:
        elapsed = time.time() - start
        mins, secs = divmod(elapsed, 60)
        cprint(f"\n{'=' * 50}", Color.RED)
        cprint(f"VSIX build FAILED in {int(mins):02d}:{secs:06.3f}", Color.RED)
        cprint(f"{'=' * 50}", Color.RED)
        cprint(f"\nError: {e}", Color.RED)
        sys.exit(1)


def cmd_spec(_args):
    _generate_mca_spec(force=True)
    _validate_mca_spec()


def cmd_test(args):
    if getattr(args, "all", False):
        _run_python_tests()
        _run_mca_tests()
    else:
        _run_mca_tests()


def cmd_all(args):
    cprint("=== Building all ===", Color.CYAN)
    cmd_spec(args)
    cmd_app(args)
    cmd_vsix(args)


def cmd_ci(args):
    cprint("=== CI pipeline ===", Color.CYAN)
    cmd_spec(args)
    cmd_test(args)
    cmd_app(args)


def cmd_clean(_args):
    script_dir = Path(__file__).resolve().parent
    try:
        build_dir = script_dir / "build"
        if build_dir.exists():
            shutil.rmtree(build_dir)
            cprint(f"Removed: {build_dir}", Color.GREEN)

        for f in ["upload.py"]:
            p = script_dir / f
            if p.exists():
                p.unlink()
                cprint(f"Removed: {p}", Color.GREEN)

        for cache_dir in sorted(script_dir.rglob("__pycache__")):
            shutil.rmtree(cache_dir, ignore_errors=True)

        cprint("Clean complete.", Color.GREEN)
    except Exception as e:
        cprint(f"Clean failed: {e}", Color.RED)
        sys.exit(1)


# ── Entry point ──────────────────────────────────────────────────────────────


def _run_dep_check():
    """Run check_deps.py --install before building. Abort on failure."""
    check_script = Path(__file__).resolve().parent / "check_deps.py"
    if not check_script.exists():
        cprint("check_deps.py not found — skipping dependency check.", Color.YELLOW)
        return

    cprint("Running dependency check + install...", Color.CYAN)
    result = subprocess.run(
        [sys.executable, str(check_script), "--install"],
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        cprint("\nBuild aborted: missing dependencies.", Color.RED)
        cprint("Install them manually:  python check_deps.py --install", Color.YELLOW)
        sys.exit(1)
    cprint("All dependencies OK.\n", Color.GREEN)


def main():
    parser = argparse.ArgumentParser(
        description="TikTok-MC-Gift build system",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify all dependencies before building (runs check_deps.py)",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("spec", help="Generate MCA language specification")
    sub.add_parser("vsix", help="Build VS Code extension (.vsix)")
    p_test = sub.add_parser("test", help="Run tests")
    p_test.add_argument(
        "--all", action="store_true", help="Run all tests (Python + MCA)"
    )

    p_app = sub.add_parser("app", help="Build application via PyInstaller")
    p_app.add_argument(
        "--installer",
        action="store_true",
        help="Also build GUI installer (NSIS on Windows, shell on Linux)",
    )
    p_app.add_argument(
        "--threads",
        type=int,
        default=None,
        help="Number of parallel build threads (default: auto)",
    )
    p_app.add_argument(
        "--use-cache",
        action="store_true",
        help="Skip building — copy executables from cache (warns on missing/outdated)",
    )
    p_app.add_argument(
        "--only",
        nargs="+",
        default=None,
        metavar="FILE",
        help="Build only the given .py file(s). Accepts task names (server, overlay, ...), "
        "source basenames (server.py) or source paths (src/python/server.py)",
    )

    p_all = sub.add_parser("all", help="Run spec + app + vsix")
    p_all.add_argument(
        "--threads",
        type=int,
        default=None,
        help="Number of parallel build threads (default: auto)",
    )
    p_all.add_argument(
        "--use-cache",
        action="store_true",
        help="Skip building — copy executables from cache (warns on missing/outdated)",
    )

    p_ci = sub.add_parser("ci", help="CI pipeline: spec + test + app")
    p_ci.add_argument(
        "--threads",
        type=int,
        default=None,
        help="Number of parallel build threads (default: auto)",
    )
    p_ci.add_argument(
        "--use-cache",
        action="store_true",
        help="Skip building — copy executables from cache (warns on missing/outdated)",
    )
    sub.add_parser("clean", help="Clean build artifacts")

    parsed = parser.parse_args()

    if parsed.check:
        _run_dep_check()

    if parsed.command == "app":
        cmd_app(parsed)
    elif parsed.command == "vsix":
        cmd_vsix(parsed)
    elif parsed.command == "spec":
        cmd_spec(parsed)
    elif parsed.command == "test":
        cmd_test(parsed)
    elif parsed.command == "all":
        cmd_all(parsed)
    elif parsed.command == "ci":
        cmd_ci(parsed)
    elif parsed.command == "clean":
        cmd_clean(parsed)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
