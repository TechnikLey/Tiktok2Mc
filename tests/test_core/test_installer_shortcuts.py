"""Tests for the GUI-first installer changes.

Verify that installer shortcuts point to GUI.exe and not start.exe.
"""

from pathlib import Path
import pytest

INSTALLER_DIR = Path(__file__).resolve().parent.parent.parent / "installer"
NSIS_SCRIPT = INSTALLER_DIR / "install.nsi"
LINUX_SCRIPT = INSTALLER_DIR / "install_linux.sh"


class TestInstallerShortcuts:
    """Verify installer defaults to GUI.exe as the user entry point."""

    def test_desktop_shortcut_points_to_gui(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        # Desktop shortcut must point to core\gui.exe
        assert '$INSTDIR\\core\\gui.exe"' in content
        # Must NOT point to start.exe for desktop
        desktop_line = [ln for ln in content.splitlines() if "$DESKTOP" in ln and "CreateShortCut" in ln]
        assert len(desktop_line) == 1
        assert "gui.exe" in desktop_line[0]
        assert "start.exe" not in desktop_line[0]

    def test_start_menu_main_shortcut_points_to_gui(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        # The main TikTok2MC.lnk should point to gui.exe
        lines = [ln for ln in content.splitlines() if "TikTok2MC.lnk" in ln]
        assert len(lines) == 1
        assert "gui.exe" in lines[0]

    def test_start_menu_has_full_system_shortcut(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        # start.exe should still be available as "Start Full System"
        lines = [ln for ln in content.splitlines() if "Start Full System" in ln]
        assert len(lines) == 1
        assert "start.exe" in lines[0]

    def test_uninstall_icon_points_to_gui(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert '"DisplayIcon" "$INSTDIR\\core\\gui.exe,0"' in content

    def test_startup_registry_points_to_gui(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert 'WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Run"' in content
        assert "$INSTDIR\\core\\gui.exe" in content


class TestLinuxInstallerShortcuts:
    """Verify Linux installer defaults to gui.bin."""

    def test_desktop_entry_points_to_gui(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        # Main desktop entry should use gui.bin
        assert "Exec=/opt/TikTok2Mc/core/gui.bin" in content

    def test_linux_has_full_system_entry(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "Exec=/opt/TikTok2Mc/start.bin" in content
        assert "Full System" in content

    def test_linux_uninstalls_both_entries(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "rm -f /usr/share/applications/tiktok2mc.desktop" in content
        assert "rm -f /usr/share/applications/tiktok2mc-fullsystem.desktop" in content
