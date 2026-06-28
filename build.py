#!/usr/bin/env python3
# ==========================================
# build.py - TikTok-MC-Gift (Parallel & Cross-Platform)
# ==========================================

import sys
import os
import hashlib
import shutil
import subprocess
import uuid
import time
import fnmatch
import ast
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

def main():
    start = time.time()

    try:
        # ----- Configuration -----
        MAX_THREADS = min(16, (os.cpu_count() or 4))
        MAX_COPY_THREADS = min(32, (os.cpu_count() or 4) * 4)
        BUILD_INSTALLER = "--installer" in sys.argv

        IS_WINDOWS = sys.platform == "win32"
        SUFFIX = ".exe" if IS_WINDOWS else ".bin"

        SCRIPT_DIR = Path(__file__).resolve().parent
        os.chdir(SCRIPT_DIR)

        OUT_DIR = SCRIPT_DIR / "build" / "release"
        CACHE_DIR = SCRIPT_DIR / "build" / "cache"
        EXE_CACHE_DIR = CACHE_DIR / "exes"
        HASH_CACHE_DIR = CACHE_DIR / "hashes"
        PARALLEL_TEMP_DIR = SCRIPT_DIR / "build" / "temp_parallel"

        # Definition of main files
        # windowed=True means no console window on Windows (--noconsole in PyInstaller)
        CORE_EXECUTABLES = [
            {"name": "app",            "src": "src/python/main.py",           "dest": "core"},
            {"name": "gui",            "src": "src/python/gui.py",            "dest": "core", "windowed": True},
            {"name": "update",         "src": "src/python/update.py",         "dest": ""},
            {"name": "server",         "src": "src/python/server.py",         "dest": "core"},
            {"name": "overlay",        "src": "src/python/overlay.py",        "dest": "core"},
            {"name": "start",          "src": "src/python/start.py",          "dest": ""},
            {"name": "test_trigger",   "src": "tests/send_trigger.py",        "dest": "test"},
        ]

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
            OUT_DIR / "version" / "1.21.11",
            OUT_DIR / "config",
            OUT_DIR / "data",
            OUT_DIR / "test",
            OUT_DIR / "logs",
            OUT_DIR / "server" / "default" / "plugins" / "MinecraftServerAPI",
            OUT_DIR / "server" / "default" / "world" / "datapacks" / "StreamingTool" / "data" / "streamingtool" / "function",
            OUT_DIR / "server" / "default" / "plugins" / "DelayedTNT",
            OUT_DIR / "hooks",
            OUT_DIR / "docs",
        ]

        for d in REQUIRED_DIRS:
            d.mkdir(parents=True, exist_ok=True)

        # Clean up stale temp dirs from previous interrupted runs
        if PARALLEL_TEMP_DIR.exists():
            shutil.rmtree(PARALLEL_TEMP_DIR, ignore_errors=True)
        PARALLEL_TEMP_DIR.mkdir(parents=True, exist_ok=True)

        # ----- Collect Build Tasks -----
        cprint("Collecting all files to compile...", Color.CYAN)
        all_build_tasks = []

        # Add main EXEs
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

        # Find and add plugins
        src_plugins_root = SCRIPT_DIR / "src" / "plugins"
        # Collect plugin hook dirs to copy raw later (not compiled to .exe)
        plugin_hook_dirs: list[Path] = []
        if src_plugins_root.exists():
            for py_file in src_plugins_root.rglob("*.py"):
                # Skip __pycache__ directories
                if "__pycache__" in str(py_file):
                    continue
                # Skip test plugins (dev-only, not for user release)
                if "test" == py_file.parent.name and py_file.parent.parent.name == "plugins":
                    continue
                # Skip plugin hooks (these are imported in-process, not exec'd)
                if "hooks" in py_file.parent.parts:
                    plugin_hook_dirs.append(py_file.parent)
                    continue
                rel = py_file.parent.relative_to(src_plugins_root)
                dest = str(Path("plugins") / rel) if str(rel) != "." else "plugins"
                # Plugin executables keep their original stem name (e.g. main.exe)
                # so that start.py can find them at plugins/<name>/main.exe
                all_build_tasks.append({
                    "name": f"{py_file.stem}{SUFFIX}",
                    "src": str(py_file),
                    "dest": dest,
                })

                # Also copy extra files if present in the same plugin folder
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
            """Resolve a dotted module name to a relative path under *src_root*.
            
            Returns a relative path (to SCRIPT_DIR) or None if external.
            """
            rel = module.replace(".", "/")
            for candidate in [f"{rel}.py", f"{rel}/__init__.py"]:
                path = src_root / candidate
                if path.exists():
                    return str(path.relative_to(SCRIPT_DIR))
            return None

        def _parent_inits(module: str) -> list[str]:
            """Return ``__init__.py`` paths for each parent package of *module*."""
            result: list[str] = []
            parts = module.replace(".", "/").split("/")
            for i in range(1, len(parts)):
                init = SCRIPT_DIR / "src" / "/".join(parts[:i]) / "__init__.py"
                if init.exists():
                    result.append(str(init.relative_to(SCRIPT_DIR)))
            return result

        def _try_resolve_local(module: str, src_root: Path, source_path: Path) -> list[str]:
            """Resolve *module* to local file paths under *src_root*.
            
            Handles relative and absolute imports.  Returns relative paths
            (to SCRIPT_DIR), including parent ``__init__.py`` files.
            """
            resolved: list[str] = []

            # --- Relative imports ---
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

            # --- Absolute imports ---
            path = _resolve_module(module, src_root)
            if path:
                resolved.append(path)
                resolved.extend(_parent_inits(module))
            return resolved

        def resolve_transitive_imports(source_path: Path) -> set[str]:
            """Walk the static import graph of *source_path* and return all files
            under ``src/`` that are reachable, as relative paths to *SCRIPT_DIR*.
            
            Only ``core.*`` and local ``src/`` imports are followed — stdlib and
            third-party modules are ignored.
            """
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

            # Unique name for cache/hash
            safe_name = str(full_src.relative_to(SCRIPT_DIR)).replace(os.sep, "_")
            hash_file = HASH_CACHE_DIR / f"{safe_name}.sha256"
            dep_hash_file = HASH_CACHE_DIR / f"{safe_name}.dep_sha256"
            cache_exe = EXE_CACHE_DIR / safe_name.replace(".py", SUFFIX)

            current_hash = sha256_file(full_src)
            need_build = True

            # Hash the transitive dependency tree (no broad core_tree_hash)
            deps = resolve_transitive_imports(full_src)

            # Include build.py itself so flag changes force a full rebuild
            build_py = SCRIPT_DIR / "build.py"

            dep_hasher = hashlib.sha256()
            dep_hasher.update(current_hash.encode())
            for dep in sorted(deps):
                dep_hasher.update(dep.encode())  # path string catches added/removed deps
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
                        proc = subprocess.Popen(
                            cmd,
                            stdout=lf,
                            stderr=subprocess.STDOUT,
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

                # Cleanup temp for this thread
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
                    # kompletter Ordner (rekursiv)
                    if pattern.endswith("/**"):
                        base = Path(pattern[:-3])
                        if base in rel.parents or rel == base:
                            return True
                    # einfache Glob-Patterns (*.md etc.)
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
        # Copy plugin hooks as raw .py (not compiled to .exe — imported in-process)
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
            ("tools/server.jar",                    "version/1.21.11/server.jar"),
            ("tools/mca.vsix",                      "core/assets/mca.vsix"),
            ("AIPrompt.md",                         "AIPrompt.md"),
        ]

        for src_rel, dst_rel in FILES:
            src_path = Path(src_rel)
            if src_path.exists():
                target = OUT_DIR / dst_rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, target)

        # Generate config.default.yaml from config.yaml with template header
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
                # Find makensis: PATH first, then common install locations
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
                        # Also copy installer into the release folder so it ships with the portable ZIP
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

                # Pack release/ into a tar.gz
                with tarfile.open(tar_path, "w:gz") as tf:
                    for entry in OUT_DIR.rglob("*"):
                        if entry.is_file():
                            tf.add(entry, arcname=entry.relative_to(OUT_DIR))

                # Build self-extracting script: header + archive
                with open(installer_out, "wb") as outf:
                    outf.write(linux_template.read_bytes())
                    outf.write(b"\n__ARCHIVE_BELOW__\n")
                    with open(tar_path, "rb") as tgf:
                        outf.write(tgf.read())

                # Make executable
                os.chmod(installer_out, 0o755)
                cprint(f"Linux installer created: {installer_out}", Color.GREEN)

                # Copy into release folder as well
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

if __name__ == "__main__":
    main()