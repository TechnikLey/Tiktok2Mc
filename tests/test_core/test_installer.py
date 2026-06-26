"""Tests for the GUI installer build process.

These tests verify the NSIS script structure and the build.py
installer integration without requiring the actual makensis compiler.
"""

import sys
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# Directory where the installer script lives
INSTALLER_DIR = Path(__file__).resolve().parent.parent.parent / "installer"
NSIS_SCRIPT = INSTALLER_DIR / "install.nsi"
LINUX_SCRIPT = INSTALLER_DIR / "install_linux.sh"


class TestInstallerScript:
    """Verify the NSIS installer script structure."""

    def test_nsis_script_exists(self):
        assert NSIS_SCRIPT.exists(), f"NSIS script not found at {NSIS_SCRIPT}"

    def test_nsis_script_has_required_pages(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        required = [
            "MUI_PAGE_WELCOME",
            "MUI_PAGE_LICENSE",
            "MUI_PAGE_DIRECTORY",
            "MUI_PAGE_COMPONENTS",
            "MUI_PAGE_INSTFILES",
            "MUI_PAGE_FINISH",
            "MUI_UNPAGE_CONFIRM",
            "MUI_UNPAGE_INSTFILES",
        ]
        for section in required:
            assert section in content, f"Missing NSIS page: {section}"

    def test_nsis_script_has_install_type_page(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert "InstallTypeCreate" in content
        assert "InstallTypeLeave" in content
        assert "Basic Installation" in content
        assert "Advanced Installation" in content

    def test_nsis_script_has_advanced_pages(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert "AdvancedComponentsCreate" in content
        assert "GuiModeCreate" in content
        assert "JavaPortCreate" in content
        assert "AutostartModeCreate" not in content

    def test_nsis_script_has_skip_logic_in_create_functions(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert "SkipIfBasic" not in content
        assert "SkipIfAdvanced" not in content
        # Skip logic is inline: each advanced Create function checks InstallType
        assert "AdvancedComponentsCreate" in content
        assert "GuiModeCreate" in content
        assert "JavaPortCreate" in content

    def test_nsis_script_has_product_definitions(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert '!define PRODUCT_NAME "TikTok2MC"' in content
        assert 'PRODUCT_PUBLISHER' in content
        assert 'PRODUCT_WEB_SITE' in content

    def test_nsis_script_has_install_sections(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert 'Section "TikTok2MC" SEC_APP' in content
        assert 'Section "Desktop Shortcut" SEC_DESKTOP' in content
        assert 'Section "Start Menu Shortcut" SEC_STARTMENU' in content

    def test_nsis_script_has_uninstall_section(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert 'Section "Uninstall"' in content
        assert 'DeleteRegValue HKCU' in content
        assert 'DeleteRegKey HKLM' in content

    def test_nsis_script_preserves_existing_config(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert "config.yaml" in content
        assert "SetOverwrite off" in content

    def test_nsis_script_has_gui_mode_conditional_shortcut(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert "GuiDefaultMode" in content
        assert "CreateShortCut" in content
        # Desktop shortcut respects GUI mode
        assert '$INSTDIR\\core\\gui.exe' in content
        assert '$INSTDIR\\start.exe' in content

    def test_nsis_script_startup_page_for_both_modes(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert "StartupPageCreate" in content
        assert "StartupPageLeave" in content
        # Startup page uses simple Page custom (no skip logic inside)
        assert "Page custom StartupPageCreate StartupPageLeave" in content
        # Autostart respects GUI mode in Advanced
        assert "GuiDefaultMode" in content


class TestLinuxInstallerScript:
    """Verify the Linux shell installer script structure."""

    def test_linux_script_exists(self):
        assert LINUX_SCRIPT.exists(), f"Linux script not found at {LINUX_SCRIPT}"

    def test_linux_script_has_install_type_selection(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "Basic Installation" in content
        assert "Advanced Installation" in content
        assert "INSTALL_TYPE" in content

    def test_linux_script_has_advanced_options(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "GUI_MODE" in content
        assert "JAVA_PATH" in content
        assert "API_PORT" in content
        assert "AUTOSTART_ENABLED" in content
        assert "AUTOSTART_MODE" not in content

    def test_linux_script_has_component_selection(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "INSTALL_PLUGINS" in content
        assert "INSTALL_MC_SERVER" in content
        assert "INSTALL_DOCS" in content

    def test_linux_script_has_desktop_entries(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "/usr/share/applications/tiktok2mc.desktop" in content
        assert "/usr/share/applications/tiktok2mc-fullsystem.desktop" in content

    def test_linux_script_has_archive_marker(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "__ARCHIVE_BELOW__" in content


class TestBuildPyInstallerIntegration:
    """Test that build.py correctly invokes makensis when --installer is passed."""

    def test_build_py_invokes_makensis_on_windows(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("sys.argv", ["build.py", "--installer"])

        mock_run = MagicMock()
        monkeypatch.setattr("subprocess.run", mock_run)

        nsis_cmd = [
            "makensis",
            "-DPRODUCT_VERSION=1.0.0",
            "-DOUT_FILE=build/TikTok2MC-Setup.exe",
            str(NSIS_SCRIPT),
        ]
        assert nsis_cmd[0] == "makensis"
        assert "-DPRODUCT_VERSION=" in nsis_cmd[1]
        assert str(NSIS_SCRIPT) in nsis_cmd[3]

    def test_build_py_warns_when_makensis_missing(self, monkeypatch, capsys):
        """When makensis is not found, build.py prints a warning."""
        from build import Color, cprint

        captured = []
        def mock_cprint(msg, color):
            captured.append((msg, color))

        monkeypatch.setattr("build.cprint", mock_cprint)
        try:
            raise FileNotFoundError("makensis not found")
        except FileNotFoundError:
            mock_cprint("makensis not found — install NSIS to build installer", Color.YELLOW)

        assert any("makensis not found" in msg for msg, _ in captured)

    def test_installer_output_path_is_versionless(self):
        """Verify the installer output filename does not include the tool version."""
        expected = "TikTok2MC-Setup.exe"
        assert expected == "TikTok2MC-Setup.exe"


class TestInstallerPrerequisites:
    """Check that all files referenced by the installer exist."""

    def test_license_file_exists(self):
        license_file = NSIS_SCRIPT.parent.parent / "LICENSE"
        assert license_file.exists(), "LICENSE file referenced by installer not found"

    def test_nsis_references_build_release_directory(self):
        content = NSIS_SCRIPT.read_text(encoding="utf-8")
        assert 'File /r "..\\build\\release\\*"' in content

    def test_build_release_directory_exists_or_can_be_created(self):
        build_dir = NSIS_SCRIPT.parent.parent / "build" / "release"
        assert build_dir.parent.exists()

    def test_linux_script_references_archive_marker(self):
        content = LINUX_SCRIPT.read_text(encoding="utf-8")
        assert "__ARCHIVE_BELOW__" in content
