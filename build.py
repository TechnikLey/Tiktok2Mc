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
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---- Colors (ANSI, works on modern Windows 10+ and Linux) ----
class Color:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    RESET = "\033[0m"

def cprint(msg, color=Color.RESET):
    print(f"{color}{msg}{Color.RESET}")

# Enable ANSI colors on Windows
if sys.platform == "win32":
    os.system("")  # enables ANSI escape sequences in Windows terminal


def main():
    start = time.time()

    try:
        # ----- Configuration -----
        MAX_THREADS = 8
        MAX_COPY_THREADS = 16
        TOOL_VERSION = "v0.2.0"
        UPDATER_VERSION = "v1.0.0"

        IS_WINDOWS = sys.platform == "win32"
        EXE_SUFFIX = ".exe" if IS_WINDOWS else ""

        SCRIPT_DIR = Path(__file__).resolve().parent
        os.chdir(SCRIPT_DIR)

        OUT_DIR = SCRIPT_DIR / "build" / "release"
        CACHE_DIR = SCRIPT_DIR / "build" / "cache"
        EXE_CACHE_DIR = CACHE_DIR / "exes"
        HASH_CACHE_DIR = CACHE_DIR / "hashes"
        PARALLEL_TEMP_DIR = SCRIPT_DIR / "build" / "temp_parallel"

        # Definition of main files
        CORE_EXECUTABLES = [
            {"name": "app",            "src": "src/python/main.py",      "dest": "core"},
            {"name": "update",         "src": "src/python/update.py",    "dest": ""},
            {"name": "gui",            "src": "src/python/gui.py",       "dest": "core"},
            {"name": "server",         "src": "src/python/server.py",    "dest": ""},
            {"name": "start",          "src": "src/python/start.py",     "dest": ""},
            {"name": "registry",       "src": "src/python/registry.py",  "dest": "plugins"},
            {"name": "test_trigger",   "src": "tests/send_trigger.py",   "dest": "test"},
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
        ]

        for d in REQUIRED_DIRS:
            d.mkdir(parents=True, exist_ok=True)

        # ----- Collect Build Tasks -----
        cprint("Collecting all files to compile...", Color.CYAN)
        all_build_tasks = []

        # Add main EXEs
        for item in CORE_EXECUTABLES:
            all_build_tasks.append({
                "name": item["name"] + EXE_SUFFIX,
                "src": item["src"],
                "dest": item["dest"],
            })

        # Find and add plugins
        src_plugins_root = SCRIPT_DIR / "src" / "plugins"
        if src_plugins_root.exists():
            for py_file in src_plugins_root.rglob("*.py"):
                # Skip cache/pycache directories
                if re.search(r"[\\/](hash|exe_cache|__pycache__)([\\/]|$)", str(py_file)):
                    continue
                rel = py_file.parent.relative_to(src_plugins_root)
                dest = str(Path("plugins") / rel) if str(rel) != "." else "plugins"
                all_build_tasks.append({
                    "name": py_file.stem + EXE_SUFFIX,
                    "src": str(py_file),
                    "dest": dest,
                })

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

        def build_one(item):
            full_src = Path(item["src"]).resolve()

            # Unique name for cache/hash
            safe_name = str(full_src.relative_to(SCRIPT_DIR)).replace(os.sep, "_")
            hash_file = HASH_CACHE_DIR / f"{safe_name}.sha256"
            cache_exe = EXE_CACHE_DIR / safe_name.replace(".py", EXE_SUFFIX)

            current_hash = sha256_file(full_src)
            need_build = True

            if hash_file.exists() and cache_exe.exists():
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
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                fresh = t_dist / item["name"]
                if fresh.exists():
                    shutil.copy2(fresh, final_path)
                    shutil.copy2(fresh, cache_exe)
                    hash_file.write_text(current_hash)
                    cprint(f"Done: {item['name']}", Color.GREEN)
                else:
                    cprint(f"FAILED: {item['name']}", Color.RED)
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

        def sync_folder(source, destination, threads=MAX_COPY_THREADS):
            src = Path(source)
            dst = Path(destination)
            if not src.exists():
                return
            dst.mkdir(parents=True, exist_ok=True)
            all_files = [f for f in src.rglob("*") if f.is_file()]

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
        sync_folder("src/event_hooks", OUT_DIR / "event_hooks")

        FILES = [
            ("static/css/style.css",              "core/static/css/style.css"),
            ("defaults/config.yaml",              "config/config.yaml"),
            ("defaults/config.default.yaml",      "config/config.default.yaml"),
            ("defaults/gifts.json",               "core/gifts.json"),
            ("LICENSE",                            "LICENSE"),
            ("README.md",                          "README.md"),
            ("defaults/actions.mca",              "data/actions.mca"),
            ("defaults/http_actions.txt",         "data/http_actions.txt"),
            ("defaults/configServerAPI.yml",      "server/mc/plugins/MinecraftServerAPI/config.yml"),
            ("defaults/DelayedTNTconfig.yml",     "server/mc/plugins/DelayedTNT/config.yml"),
            ("tools/MinecraftServerAPI-1.21.x.jar", "server/mc/plugins/MinecraftServerAPI-1.21.x.jar"),
            ("tools/DelayedTNT.jar",              "server/mc/plugins/DelayedTNT.jar"),
            ("tools/server.jar",                  "server/mc/server.jar"),
        ]

        for src_rel, dst_rel in FILES:
            src_path = Path(src_rel)
            if src_path.exists():
                target = OUT_DIR / dst_rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, target)

        # ----- Metadata & Cleanup -----
        cprint("Cleaning up temporary files...", Color.CYAN)
        (OUT_DIR / "version.txt").write_text(
            f"ToolVersion: {TOOL_VERSION}\nUpdaterVersion: {UPDATER_VERSION}\n",
            encoding="utf-8",
        )

        if PARALLEL_TEMP_DIR.exists():
            shutil.rmtree(PARALLEL_TEMP_DIR, ignore_errors=True)

        for cache_dir in ["src/core/__pycache__", "src/python/__pycache__"]:
            p = Path(cache_dir)
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)

        # ----- Release / Upload Script -----
        cprint("Creating upload.py...", Color.CYAN)
        upload_content = (
            '#!/usr/bin/env python3\n'
            'import subprocess\n'
            'import sys\n'
            'import os\n'
            'from pathlib import Path\n'
            '\n'
            f'TOOL_VERSION = "{TOOL_VERSION}"\n'
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
            '    print(f"{C}> {\' \'.join(cmd)}{X}")\n'
            '    return subprocess.run(cmd, check=check, capture_output=False)\n'
            '\n'
            '# 1. Stage all changes\n'
            'print(f"\\n{C}Staging changes...{X}")\n'
            'run(["git", "add", "-A"])\n'
            '\n'
            '# 2. Commit (ask for message)\n'
            f'msg = input(f"\\n{{Y}}Commit message (Enter = \'Release {TOOL_VERSION}\'): {{X}}").strip()\n'
            'if not msg:\n'
            f'    msg = "Release {TOOL_VERSION}"\n'
            'result = run(["git", "commit", "-m", msg], check=False)\n'
            'if result.returncode != 0:\n'
            '    print(f"{Y}No changes to commit, continuing...{X}")\n'
            '\n'
            '# 3. Push\n'
            'print(f"\\n{C}Pushing to remote...{X}")\n'
            'run(["git", "push"])\n'
            '\n'
            '# 4. Create and push tag\n'
            f'print(f"\\n{{C}}Creating tag {TOOL_VERSION}...{{X}}")\n'
            f'run(["git", "tag", "-d", "{TOOL_VERSION}"], check=False)\n'
            f'run(["git", "push", "origin", "--delete", "{TOOL_VERSION}"], check=False)\n'
            f'run(["git", "tag", "{TOOL_VERSION}"])\n'
            f'run(["git", "push", "origin", "{TOOL_VERSION}"])\n'
            '\n'
            f'print(f"\\n{{G}}Done! GitHub Actions will now build & release {TOOL_VERSION}{{X}}")\n'
            'print(f"{C}   Check progress: https://github.com/<OWNER>/<REPO>/actions{X}")\n'
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