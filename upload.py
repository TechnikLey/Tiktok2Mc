#!/usr/bin/env python3
import os
import subprocess
import sys
import shutil
from pathlib import Path

TOOL_VERSION = "v0.1.0"
RELEASE_ZIP = Path("build/v0.1.0.zip")
OUT_DIR = Path("build\release")

os.chdir(Path(__file__).resolve().parent)

if not RELEASE_ZIP.exists():
    print("\033[96m📦 Creating ZIP...\033[0m")
    shutil.make_archive(str(RELEASE_ZIP.with_suffix("")), "zip", "build", "release")

result = subprocess.run(["gh", "release", "view", TOOL_VERSION], capture_output=True)
if result.returncode == 0:
    subprocess.run(["gh", "release", "delete", TOOL_VERSION, "--yes"], check=True)
    import time; time.sleep(2)

subprocess.run([
    "gh", "release", "create", TOOL_VERSION, str(RELEASE_ZIP),
    "--title", TOOL_VERSION, "--notes", f"Release {TOOL_VERSION}"
], check=True)

input("\nPress Enter to exit...")
