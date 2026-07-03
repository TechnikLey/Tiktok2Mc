#!/usr/bin/env python3
# ==========================================
# build.py - TikTok-MC-Gift (Parallel & Cross-Platform)
#
# Usage:
#   python build.py <command> [options]
#
# Commands:
#   app              Build application (PyInstaller)
#   vsix             Build VS Code extension (.vsix)
#   spec             Generate MCA language specification
#   test             Run tests (MCA / Python)
#   all              Run spec + app + vsix
#   ci               CI pipeline (validate + test + spec + app)
#   clean            Clean build artifacts
# ==========================================

import sys
import os
import hashlib
import json
import shutil
import subprocess
import uuid
import time
import fnmatch
import ast
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)
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

def _kill_proc_tree(pid):
    """Kill a process and all descendants (Windows)."""
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], check=False, capture_output=True)
        except Exception:
            pass

# Enable ANSI colors on Windows
if sys.platform == "win32":
    os.system("")  # enables ANSI escape sequences in Windows terminal

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from core.version import TOOL_VERSION, UPDATER_VERSION

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
        cache = Path(__file__).resolve().parent / "build" / "cache" / "mca_spec_hashes.json"
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
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"MCA spec generation failed:\n{result.stderr.strip()}"
        )
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

    required = ["version", "event_triggers", "command_prefixes", "diagnostic_codes",
                 "placeholders", "patterns", "validation_rules"]
    missing = [k for k in required if k not in data]
    if missing:
        raise RuntimeError(f"MCA spec missing required fields: {', '.join(missing)}")

    if not isinstance(data.get("event_triggers"), list) or len(data["event_triggers"]) == 0:
        raise RuntimeError("MCA spec: event_triggers must be a non-empty list")

    if not isinstance(data.get("command_prefixes"), dict) or len(data["command_prefixes"]) == 0:
        raise RuntimeError("MCA spec: command_prefixes must be a non-empty dict")

    if not isinstance(data.get("diagnostic_codes"), list) or len(data["diagnostic_codes"]) == 0:
        raise RuntimeError("MCA spec: diagnostic_codes must be a non-empty list")

    cprint("MCA specification valid.", Color.GRAY)


def _run_mca_tests() -> None:
    """Run the MCA language server test suite.
    
    Raises RuntimeError if any test fails.
    """
    test_runner = Path(__file__).resolve().parent / MCA_SERVER_TEST_DIR / "run.js"
    if not test_runner.exists():
        raise RuntimeError(f"MCA test runner not found: {test_runner}")

    cprint("Running MCA language server tests...", Color.CYAN)
    result = subprocess.run(
        ["node", str(test_runner)],
        capture_output=True, text=True, timeout=60,
    )
    # Print test output regardless of pass/fail
    for line in result.stdout.strip().split("\n"):
        cprint(f"  {line}", Color.GRAY if "PASS" in line else (
            Color.RED if "FAIL" in line else Color.GRAY))

    if result.returncode != 0 or "FAIL" in result.stdout:
        raise RuntimeError("MCA language server tests FAILED.")
    cprint("All MCA language server tests passed.", Color.GREEN)


def _find_vsce() -> str:
    """Locate the vsce CLI tool path."""
    npm_dir = Path(os.environ.get("APPDATA", "")) / "npm"

    # Check for vsce.cmd (Windows) or vsce (Unix)
    for name in ["vsce.cmd", "vsce"]:
        p = npm_dir / name
        if p.exists():
            return str(p)

    # Check via npx
    for npx_name in ["npx.cmd", "npx"]:
        npx_path = shutil.which(npx_name)
        if npx_path:
            return f"{npx_path} --yes @vscode/vsce"

    raise RuntimeError(
        "vsce not found. Install it: npm install -g @vscode/vsce"
    )


def _package_vsix(extension_dir: Path) -> Path:
    """Package the VSIX extension.
    
    Returns the path to the generated .vsix file.
    Raises RuntimeError on failure.
    """
    vsce_cmd = _find_vsce()
    cprint("Packaging VSIX...", Color.CYAN)

    # vsce outputs the vsix to the current directory
    result = subprocess.run(
        vsce_cmd.split() + ["package", "--allow-missing-repository"],
        capture_output=True, text=True, timeout=120,
        cwd=str(extension_dir),
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
            raise RuntimeError(
                f"VSIX packaging failed:\n{result.stderr.strip()}"
            )
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
    BUILD_INSTALLER = getattr(args, 'installer', False)

    IS_WINDOWS = sys.platform == "win32"
    SUFFIX = ".exe" if IS_WINDOWS else ".bin"

    SCRIPT_DIR = Path(__file__).resolve().parent
    os.chdir(SCRIPT_DIR)

    OUT_DIR = SCRIPT_DIR / "build" / "release"
    CACHE_DIR = SCRIPT_DIR / "build" / "cache"
    EXE_CACHE_DIR = CACHE_DIR / "exes"
    HASH_CACHE_DIR = CACHE_DIR / "hashes"
    PARALLEL_TEMP_DIR = SCRIPT_DIR / "build" / "temp_parallel"

    MAX_THREADS = min(16, (os.cpu_count() or 4))
    MAX_COPY_THREADS = min(32, (os.cpu_count() or 4) * 4)

    CORE_EXECUTABLES = [
        {"name": "app",            "src": "src/python/main.py",           "dest": "core"},
        {"name": "gui",            "src": "src/python/gui.py",            "dest": "core", "windowed": True},
        {"name": "update",         "src": "src/python/update.py",         "dest": ""},
        {"name": "server",         "src": "src/python/server.py",         "dest": "core"},
        {"name": "overlay",        "src": "src/python/overlay.py",        "dest": "core"},
        {"name": "start",          "src": "src/python/start.py",          "dest": ""},
        {"name": "test_trigger",   "src": "src/python/send_trigger.py",    "dest": "test"},
    ]

    try:
        # ----- Preparation & Directory Structure -----
        cprint("Preparing build environment...", Color.CYAN)

        if OUT_DIR.exists():
            shutil.rmtree(OUT_DIR)

        REQUIRED_DIRS = [
            EXE_CACHE_DIR, HASH_CACHE_DIR, OUT_DIR, PARALLEL_TEMP_DIR,
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
            OUT_DIR / "server" / "datapack" / "StreamingTool" / "data" / "streamingtool" / "function",
            OUT_DIR / "server" / "default" / "plugins" / "DelayedTNT",
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
            all_build_tasks.append(task)

        src_plugins_root = SCRIPT_DIR / "src" / "plugins"
        plugin_hook_dirs: list[Path] = []
        if src_plugins_root.exists():
            for py_file in src_plugins_root.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                if "test" == py_file.parent.name and py_file.parent.parent.name == "plugins":
                    continue
                if "hooks" in py_file.parent.parts:
                    plugin_hook_dirs.append(py_file.parent)
                    continue
                rel = py_file.parent.relative_to(src_plugins_root)
                dest = str(Path("plugins") / rel) if str(rel) != "." else "plugins"
                all_build_tasks.append({
                    "name": f"{py_file.stem}{SUFFIX}",
                    "src": str(py_file),
                    "dest": dest,
                })

                for extra_file in ["plugin.json", "version.txt", "README.md", "config.yaml"]:
                    extra_path = py_file.parent / extra_file
                    if extra_path.exists():
                        target_dir = OUT_DIR / dest
                        target_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(extra_path, target_dir / extra_file)

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

        def _try_resolve_local(module: str, src_root: Path, source_path: Path) -> list[str]:
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

        def build_one(item):
            full_src = Path(item["src"]).resolve()
            safe_name = str(full_src.relative_to(SCRIPT_DIR)).replace(os.sep, "_")
            hash_file = HASH_CACHE_DIR / f"{safe_name}.sha256"
            dep_hash_file = HASH_CACHE_DIR / f"{safe_name}.dep_sha256"
            cache_exe = EXE_CACHE_DIR / safe_name.replace(".py", SUFFIX)

            current_hash = sha256_file(full_src)
            need_build = True

            deps = resolve_transitive_imports(full_src)
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
            combined_hash = dep_hasher.hexdigest()

            if (hash_file.exists() and dep_hash_file.exists() and cache_exe.exists()):
                if (hash_file.read_text().strip() == current_hash and
                    dep_hash_file.read_text().strip() == combined_hash):
                    need_build = False

            target_dir = OUT_DIR if not item["dest"] else OUT_DIR / item["dest"]
            target_dir.mkdir(parents=True, exist_ok=True)
            final_path = target_dir / item["name"]

            if need_build:
                cprint(f"[Parallel] Compiling: {item['name']}...", Color.YELLOW)

                unique_id = uuid.uuid4().hex[:8]
                t_dist = PARALLEL_TEMP_DIR / f"dist_{unique_id}"
                t_work = PARALLEL_TEMP_DIR / f"work_{unique_id}"
                t_spec = PARALLEL_TEMP_DIR / f"spec_{unique_id}"
                log_file = PARALLEL_TEMP_DIR / f"log_{unique_id}.txt"

                cmd = [
                    sys.executable, "-m", "PyInstaller",
                    "--onefile",
                    "--path=src",
                    str(full_src),
                    "--name", item["name"].replace(SUFFIX, ""),
                    "--distpath", str(t_dist),
                    "--workpath", str(t_work),
                    "--specpath", str(t_spec),
                    "--noconfirm",
                    "--log-level", "ERROR",
                    "--hidden-import=_multiprocessing",
                ]
                if item.get("windowed"):
                    cmd.append("--noconsole")

                try:
                    with open(log_file, "w", encoding="utf-8") as lf:
                        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
                        try:
                            return_code = proc.wait(timeout=600)
                        except subprocess.TimeoutExpired:
                            _kill_proc_tree(proc.pid)
                            cprint(f"TIMEOUT: {item['name']} after 600s", Color.RED)
                            if log_file.exists():
                                cprint(log_file.read_text(errors="replace"), Color.RED)
                            return False
                except Exception as e:
                    cprint(f"ERROR running PyInstaller for {item['name']}: {e}", Color.RED)
                    return False

                if return_code != 0:
                    cprint(f"FAILED: {item['name']} (exit code {return_code})", Color.RED)
                    if log_file.exists():
                        cprint(log_file.read_text(errors="replace"), Color.RED)
                    return False

                fresh = t_dist / item["name"]
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

        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            futures = {executor.submit(build_one, task): task for task in all_build_tasks}
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

        # ----- Assets & Resources -----
        cprint(f"\nSynchronizing assets and resources with {MAX_COPY_THREADS} threads...", Color.CYAN)

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
                f for f in src.rglob("*")
                if f.is_file() and not is_excluded(f)
            ]
            def copy_one(f):
                rel = f.relative_to(src)
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
            with ThreadPoolExecutor(max_workers=threads) as pool:
                pool.map(copy_one, all_files)

        sync_folder("assets",          OUT_DIR / "core" / "assets")
        sync_folder("templates",          OUT_DIR / "core" / "templates")
        sync_folder("tools/Java",      OUT_DIR / "server" / "java")
        sync_folder("src/hooks", OUT_DIR / "hooks", exclude=["example_hook/**"])
        for hook_src_dir in set(plugin_hook_dirs):
            rel_hook = hook_src_dir.relative_to(SCRIPT_DIR / "src")
            sync_folder(hook_src_dir, OUT_DIR / rel_hook)
        sync_folder("docs", OUT_DIR / "docs", exclude=["public/**", ".gitignore"])

        FILES = [
            ("defaults/config.yaml",                "config/config.yaml"),
            ("defaults/gifts.json",                 "core/gifts.json"),
            ("LICENSE",                             "LICENSE"),
            ("README.md",                           "README.md"),
            ("defaults/actions.mca",                "data/actions.mca"),
            ("defaults/configServerAPI.yml",        "server/default/plugins/MinecraftServerAPI/config.yml"),
            ("defaults/DelayedTNTconfig.yml",       "server/default/plugins/DelayedTNT/config.yml"),
            ("tools/MinecraftServerAPI-1.21.x.jar", "server/default/plugins/MinecraftServerAPI-1.21.x.jar"),
            ("tools/DelayedTNT.jar",                "server/default/plugins/DelayedTNT.jar"),
            ("tools/server.jar",                    "server/default/server.jar"),
            ("tools/server.jar",                    "versions/1.21.11/server.jar"),
            ("tools/mca.vsix",                      "core/assets/mca.vsix"),
            ("AIPrompt.md",                         "AIPrompt.md"),
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
            '#!/usr/bin/env python3\n'
            'import subprocess\n'
            'import sys\n'
            'import os\n'
            'from pathlib import Path\n'
            'import logging\n'
            '\n'
            'logging.basicConfig(level=logging.INFO, format=\'%(message)s\', stream=sys.stdout)\n'
            'log = logging.getLogger(__name__)\n'
            '\n'
            '_src = Path(__file__).resolve().parent / "src"\n'
            'if str(_src) not in sys.path:\n'
            '    sys.path.insert(0, str(_src))\n'
            '\n'
            'from core.version import TOOL_VERSION\n'
            '\n'
            'os.chdir(Path(__file__).resolve().parent)\n'
            '\n'
            'C = "\\033[96m"\n'
            'G = "\\033[92m"\n'
            'Y = "\\033[93m"\n'
            'R = "\\033[91m"\n'
            'X = "\\033[0m"\n'
            '\n'
            'def run(cmd, check=True):\n'
            '    log.info(f"{C}> {\' \'.join(cmd)}{X}")\n'
            '    return subprocess.run(cmd, check=check, capture_output=False)\n'
            '\n'
            '# 1. Stage all changes\n'
            'log.info(f"\\n{C}Staging changes...{X}")\n'
            'run(["git", "add", "-A"])\n'
            '\n'
            '# 2. Commit (ask for message)\n'
            f'msg = input(f"\\n{{Y}}Commit message (Enter = \'Release {TOOL_VERSION}\'): {{X}}").strip()\n'
            'if not msg:\n'
            f'    msg = "Release {TOOL_VERSION}"\n'
            'result = run(["git", "commit", "-m", msg], check=False)\n'
            'if result.returncode != 0:\n'
            '    log.info(f"{Y}No changes to commit, continuing...{X}")\n'
            '\n'
            '# 3. Push\n'
            'log.info(f"\\n{C}Pushing to remote...{X}")\n'
            'run(["git", "push"])\n'
            '\n'
            '# 4. Create and push tag\n'
            f'log.info(f"\\n{{C}}Creating tag {TOOL_VERSION}...{{X}}")\n'
            f'run(["git", "tag", "-d", "{TOOL_VERSION}"], check=False)\n'
            f'run(["git", "push", "origin", "--delete", "{TOOL_VERSION}"], check=False)\n'
            f'run(["git", "tag", "{TOOL_VERSION}"])\n'
            f'run(["git", "push", "origin", "{TOOL_VERSION}"])\n'
            '\n'
            f'log.info(f"\\n{{G}}Done! GitHub Actions will now build & release {TOOL_VERSION}{{X}}")\n'
            'log.info(f"{C}   Check progress: https://github.com/<OWNER>/<REPO>/actions{X}")\n'
            '\n'
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
                makensis_cmd = "makensis"
                try:
                    _sp.run(["makensis", "/VERSION"], check=False, capture_output=True)
                except FileNotFoundError:
                    for nsis_path in [
                        Path("C:/Program Files (x86)/NSIS/Bin/makensis.exe"),
                        Path("C:/Program Files/NSIS/Bin/makensis.exe"),
                        Path(os.environ.get("LOCALAPPDATA", "")) / "NSIS" / "Bin" / "makensis.exe",
                    ]:
                        if nsis_path.exists():
                            makensis_cmd = str(nsis_path)
                            break
                    else:
                        cprint("makensis not found — install NSIS or restart your terminal", Color.YELLOW)
                        makensis_cmd = None

                if makensis_cmd:
                    try:
                        _sp.run(
                            [makensis_cmd,
                             f"-DPRODUCT_VERSION={TOOL_VERSION}",
                             f"-DOUT_FILE={installer_out}",
                             str(nsis_script)],
                            check=True, capture_output=True,
                        )
                        cprint(f"Installer created: {installer_out}", Color.GREEN)
                        installer_in_release = OUT_DIR / installer_out.name
                        shutil.copy2(installer_out, installer_in_release)
                        cprint(f"Installer copied to release: {installer_in_release}", Color.GREEN)
                    except _sp.CalledProcessError as e:
                        cprint(f"Installer build failed: {e.stderr.decode(errors='replace')}", Color.RED)
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
                        if entry.is_file():
                            tf.add(entry, arcname=entry.relative_to(OUT_DIR))

                with open(installer_out, "wb") as outf:
                    outf.write(linux_template.read_bytes())
                    outf.write(b"\n__ARCHIVE_BELOW__\n")
                    with open(tar_path, "rb") as tgf:
                        outf.write(tgf.read())

                os.chmod(installer_out, 0o755)
                cprint(f"Linux installer created: {installer_out}", Color.GREEN)

                installer_in_release = OUT_DIR / installer_out.name
                shutil.copy2(installer_out, installer_in_release)
                cprint(f"Installer copied to release: {installer_in_release}", Color.GREEN)
            else:
                cprint(f"Linux installer template not found at {linux_template}", Color.YELLOW)

        # --- Finish ---
        elapsed = time.time() - start
        minutes, seconds = divmod(elapsed, 60)
        cprint(f"\n======================================", Color.GREEN)
        cprint(f"Build completed in {int(minutes):02d}:{seconds:06.3f}", Color.GREEN)
        cprint(f"======================================", Color.GREEN)

    except Exception as e:
        elapsed = time.time() - start
        minutes, seconds = divmod(elapsed, 60)
        cprint(f"\n======================================", Color.RED)
        cprint(f"Build FAILED in {int(minutes):02d}:{seconds:06.3f}", Color.RED)
        cprint(f"======================================", Color.RED)
        cprint(f"\nError message:", Color.YELLOW)
        cprint(str(e), Color.RED)
        cprint(f"======================================", Color.RED)
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


def cmd_test(_args):
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

def main():
    parser = argparse.ArgumentParser(
        description="TikTok-MC-Gift build system",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("spec", help="Generate MCA language specification")
    sub.add_parser("vsix", help="Build VS Code extension (.vsix)")
    sub.add_parser("test", help="Run MCA language server tests")

    p_app = sub.add_parser("app", help="Build application via PyInstaller")
    p_app.add_argument("--installer", action="store_true",
                       help="Also build GUI installer (NSIS on Windows, shell on Linux)")

    sub.add_parser("all", help="Run spec + app + vsix")
    sub.add_parser("ci", help="CI pipeline: spec + test + app")
    sub.add_parser("clean", help="Clean build artifacts")

    parsed = parser.parse_args()

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