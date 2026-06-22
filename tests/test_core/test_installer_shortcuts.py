"""Tests for the GUI-first installer changes.

Verify that installer shortcuts point to GUI.exe/start.exe
depending on installation type and GUI default mode.
"""

from pathlib import Path
import pytest

INSTALLER_DIR = Path(__file__).resolve().parent.parent.parent / "installer"
NSIS_SCRIPT = INSTALLER_DIR / "install.nsi"
LINUX_SCRIPT = INSTALLER_DIR / "install_linux.sh"


class TestInstallerShortcuts:
    """Verify installer defaults to GUI.exe as the user entry point."""

    def test_desktop_shortcut_can_point_to_gui_or_start(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        # The script contains both gui.exe and start.exe variants
        assert '$INSTDIR\\core\\gui.exe' in content
        assert '$INSTDIR\\start.exe' in content
        # GuiDefaultMode controls which one is used
        assert "GuiDefaultMode" in content

    def test_desktop_shortcut_basic_uses_gui(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        # In basic mode, desktop shortcut always goes to gui.exe
        lines = [ln for ln in content.splitlines() if "$DESKTOP" in ln and "CreateShortCut" in ln]
        assert len(lines) >= 1
        # The basic branch is: If $InstallType == 0 → gui.exe
        assert '${If} $InstallType == 0' in content
        assert 'CreateShortCut "$DESKTOP\\${PRODUCT_NAME}.lnk" "$INSTDIR\\core\\gui.exe"' in content

    def test_start_menu_main_shortcut_respects_gui_mode(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        # Start menu also uses GuiDefaultMode
        lines = [ln for ln in content.splitlines() if "TikTok2MC.lnk" in ln]
        assert len(lines) >= 1
        assert "GuiDefaultMode" in content

    def test_start_menu_has_full_system_shortcut(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        lines = [ln for ln in content.splitlines() if "Start Full System" in ln]
        assert len(lines) >= 1
        assert "start.exe" in content

    def test_uninstall_icon_points_to_gui(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert '"DisplayIcon" "$INSTDIR\\core\\gui.exe,0"' in content

    def test_startup_registry_points_to_gui_or_start(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert 'WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Run"' in content
        assert "$INSTDIR\\core\\gui.exe" in content
        assert "$INSTDIR\\start.exe" in content

    def test_startup_uses_gui_mode_for_advanced(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        # Advanced mode autostart respects GuiDefaultMode
        assert '${If} $GuiDefaultMode == 1' in content
        assert '$INSTDIR\\start.exe' in content
        assert '$INSTDIR\\core\\gui.exe' in content


class TestLinuxInstallerShortcuts:
    """Verify Linux installer respects GUI mode selection."""

    def test_linux_has_gui_mode_variable(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "GUI_MODE" in content
        assert "gui.bin" in content
        assert "start.bin" in content

    def test_linux_desktop_entry_respects_gui_mode(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        # The desktop entry file is conditionally written
        assert "gui.bin" in content
        assert "start.bin" in content
        # Both main and full-system entries exist
        assert "/opt/TikTok2Mc/start.bin" in content

    def test_linux_has_full_system_entry(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "tiktok2mc-fullsystem.desktop" in content
        assert "Full System" in content

    def test_linux_uninstalls_both_entries(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "rm -f /usr/share/applications/tiktok2mc.desktop" in content
        assert "rm -f /usr/share/applications/tiktok2mc-fullsystem.desktop" in content

    def test_linux_has_autostart_config(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "AUTOSTART_ENABLED" in content
        assert "AUTOSTART_MODE" not in content
        assert ".config/autostart" in content

    def test_linux_uses_gui_mode_for_autostart(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        # Autostart uses GUI_MODE variable (not separate mode selection)
        assert 'Exec=/opt/TikTok2Mc/${GUI_MODE}' in content

    def test_linux_has_component_selection(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "INSTALL_PLUGINS" in content
        assert "INSTALL_MC_SERVER" in content
        assert "INSTALL_DOCS" in content
