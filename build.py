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
        MAX_THREADS = 8
        MAX_COPY_THREADS = 16

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
        CORE_EXECUTABLES = [
            {"name": "app",            "src": "src/python/main.py",           "dest": "core"},
            {"name": "gui",            "src": "src/python/gui.py",            "dest": ""},
            {"name": "update",         "src": "src/python/update.py",         "dest": ""},
            {"name": "server",         "src": "src/python/server.py",         "dest": "",},
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
            OUT_DIR / "server" / "mc",
            OUT_DIR / "config",
            OUT_DIR / "data",
            OUT_DIR / "test",
            OUT_DIR / "logs",
            OUT_DIR / "server" / "mc" / "plugins" / "MinecraftServerAPI",
            OUT_DIR / "server" / "mc" / "world" / "datapacks" / "StreamingTool" / "data" / "streamingtool" / "function",
            OUT_DIR / "server" / "mc" / "plugins" / "DelayedTNT",
            OUT_DIR / "event_hooks",
            OUT_DIR / "docs",
        ]

        for d in REQUIRED_DIRS:
            d.mkdir(parents=True, exist_ok=True)

        # ----- Collect Build Tasks -----
        cprint("Collecting all files to compile...", Color.CYAN)
        all_build_tasks = []

        # Add main EXEs
        for item in CORE_EXECUTABLES:
            suffix = item.get("suffix", SUFFIX)
            all_build_tasks.append({
                "name": item["name"] + suffix,
                "src": item["src"],
                "dest": item["dest"],
            })

        # Find and add plugins
        src_plugins_root = SCRIPT_DIR / "src" / "plugins"
        if src_plugins_root.exists():
            for py_file in src_plugins_root.rglob("*.py"):
                # Skip __pycache__ directories
                if "__pycache__" in str(py_file):
                    continue
                # Skip test plugins (dev-only, not for user release)
                if "test" == py_file.parent.name and py_file.parent.parent.name == "plugins":
                    continue
                rel = py_file.parent.relative_to(src_plugins_root)
                dest = str(Path("plugins") / rel) if str(rel) != "." else "plugins"
                all_build_tasks.append({
                    "name": py_file.stem + SUFFIX,
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

        def compute_core_hash():
            """Compute a combined SHA256 of all src/core/**/*.py files.
            If any core module changes, all dependent executables must rebuild."""
            h = hashlib.sha256()
            core_dir = SCRIPT_DIR / "src" / "core"
            if core_dir.exists():
                files = sorted(core_dir.rglob("*.py"))
                for f in files:
                    h.update(f.read_bytes())
            return h.hexdigest()

        core_hash = compute_core_hash()
        core_hash_file = HASH_CACHE_DIR / "core.sha256"
        core_hash_changed = True
        if core_hash_file.exists():
            if core_hash_file.read_text().strip() == core_hash:
                core_hash_changed = False
        core_hash_file.write_text(core_hash)

        def build_one(item):
            full_src = Path(item["src"]).resolve()

            # Unique name for cache/hash
            safe_name = str(full_src.relative_to(SCRIPT_DIR)).replace(os.sep, "_")
            hash_file = HASH_CACHE_DIR / f"{safe_name}.sha256"
            cache_exe = EXE_CACHE_DIR / safe_name.replace(".py", SUFFIX)

            current_hash = sha256_file(full_src)
            need_build = True

            if hash_file.exists() and cache_exe.exists() and not core_hash_changed:
                if hash_file.read_text().strip() == current_hash:
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

                cmd = [
                    sys.executable, "-m", "PyInstaller",
                    "--onefile",
                    "--path=src",
                    str(full_src),
                    "--name", item["name"],
                    "--distpath", str(t_dist),
                    "--workpath", str(t_work),
                    "--specpath", str(t_spec),
                    "--noconfirm",
                    "--log-level", "ERROR",
                ]

                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )

                fresh = t_dist / item["name"]
                if fresh.exists():
                    shutil.copy2(fresh, final_path)
                    shutil.copy2(fresh, cache_exe)
                    hash_file.write_text(current_hash)
                    cprint(f"Done: {item['name']}", Color.GREEN)
                else:
                    cprint(f"FAILED: {item['name']}", Color.RED)
                    if result.stdout:
                        cprint(result.stdout.decode(errors="replace"), Color.RED)
                    return False

                # Cleanup temp for this thread
                for p in (t_dist, t_work, t_spec):
                    shutil.rmtree(p, ignore_errors=True)
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
        sync_folder("templates",       OUT_DIR / "core" / "templates")
        sync_folder("tools/Java",      OUT_DIR / "server" / "java")
        sync_folder("src/event_hooks", OUT_DIR / "event_hooks", exclude=["example_hook.py"])
        sync_folder("docs",            OUT_DIR / "docs", exclude=["public/**", ".gitignore"])

        FILES = [
            ("static/css/style.css",                "core/static/css/style.css"),
            ("defaults/config.yaml",                "config/config.yaml"),
            ("defaults/gifts.json",                 "core/gifts.json"),
            ("LICENSE",                             "LICENSE"),
            ("README.md",                           "README.md"),
            ("defaults/actions.mca",                "data/actions.mca"),
            ("defaults/shell_actions.txt",           "data/shell_actions.txt"),
            ("defaults/configServerAPI.yml",        "server/mc/plugins/MinecraftServerAPI/config.yml"),
            ("defaults/DelayedTNTconfig.yml",       "server/mc/plugins/DelayedTNT/config.yml"),
            ("tools/MinecraftServerAPI-1.21.x.jar", "server/mc/plugins/MinecraftServerAPI-1.21.x.jar"),
            ("tools/DelayedTNT.jar",                "server/mc/plugins/DelayedTNT.jar"),
            ("tools/server.jar",                    "server/mc/server.jar"),
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