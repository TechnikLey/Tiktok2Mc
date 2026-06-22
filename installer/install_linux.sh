#!/bin/bash
# ============================================================
# TikTok2Mc — Self-Extracting Linux Installer
# ============================================================
# This script extracts the embedded archive and installs
# TikTok2Mc to /opt/TikTok2Mc.
#
# Usage:
#   chmod +x TikTok2Mc-<version>-Linux-Setup.sh
#   sudo ./TikTok2Mc-<version>-Linux-Setup.sh
# ============================================================

set -e

INSTALL_DIR="/opt/TikTok2Mc"
BIN_LINK="/usr/local/bin/tiktok2mc"
APP_NAME="TikTok2Mc"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# --- Check root ---
if [ "$EUID" -ne 0 ]; then
    log_error "This installer must be run as root (use sudo)."
    exit 1
fi

# --- Welcome ---
echo ""
echo "=========================================="
echo "  TikTok2Mc Linux Installer"
echo "=========================================="
echo ""
log_info "Installing to: $INSTALL_DIR"

# --- Installation Type ---
echo ""
echo "Select installation type:"
echo "  1) Basic Installation (recommended)"
echo "     Installs TikTok2Mc with standard settings. Suitable for most users."
echo "  2) Advanced Installation"
echo "     Configure components, GUI mode, Java path, port, and autostart."
echo ""
read -p "Choice [1]: " INSTALL_TYPE
INSTALL_TYPE=${INSTALL_TYPE:-1}

GUI_MODE="gui.bin"    # default
INSTALL_PLUGINS=true
INSTALL_MC_SERVER=true
INSTALL_DOCS=true
JAVA_PATH=""
API_PORT="29185"
AUTOSTART_ENABLED=false

if [ "$INSTALL_TYPE" = "2" ]; then
    echo ""
    echo "--- Advanced Configuration ---"

    # GUI Default Mode
    echo ""
    echo "GUI Default Mode (for desktop shortcut):"
    echo "  1) GUI Mode (gui.bin) — Opens the graphical user interface (recommended)"
    echo "  2) Full System Mode (start.bin) — Starts the complete stack"
    read -p "Choice [1]: " gui_choice
    gui_choice=${gui_choice:-1}
    if [ "$gui_choice" = "2" ]; then
        GUI_MODE="start.bin"
    fi

    # Components
    echo ""
    echo "Optional components (y/n):"
    read -p "  Install Plugins (deathcounter, spotify, timer, wincounter) [Y]: " comp_plugins
    comp_plugins=${comp_plugins:-Y}
    [ "$comp_plugins" != "Y" ] && [ "$comp_plugins" != "y" ] && INSTALL_PLUGINS=false

    read -p "  Install Minecraft Server files [Y]: " comp_mc
    comp_mc=${comp_mc:-Y}
    [ "$comp_mc" != "Y" ] && [ "$comp_mc" != "y" ] && INSTALL_MC_SERVER=false

    read -p "  Install Documentation [Y]: " comp_docs
    comp_docs=${comp_docs:-Y}
    [ "$comp_docs" != "Y" ] && [ "$comp_docs" != "y" ] && INSTALL_DOCS=false

    # Java path
    echo ""
    read -p "Java executable path (leave empty for auto-detect): " JAVA_PATH

    # API port
    echo ""
    read -p "API server port [29185]: " user_port
    API_PORT=${user_port:-29185}

    # Autostart
    echo ""
    read -p "  Enable autostart on login? (y/n) [n]: " autostart_en
    autostart_en=${autostart_en:-n}
    if [ "$autostart_en" = "Y" ] || [ "$autostart_en" = "y" ]; then
        AUTOSTART_ENABLED=true
    fi
fi

# --- Java check ---
if command -v java &> /dev/null; then
    JAVA_VER=$(java -version 2>&1 | awk -F '"' 'NR==1 {print $2}')
    log_ok "Java found: $JAVA_VER"
else
    log_warn "Java not found. TikTok2Mc includes Java auto-detection,"
    log_warn "but you may need to install OpenJDK 17+ manually:"
    log_warn "  Debian/Ubuntu: sudo apt install openjdk-17-jre"
    log_warn "  Fedora:        sudo dnf install java-17-openjdk"
    log_warn "  Arch:          sudo pacman -S jre17-openjdk"
fi

# --- Extract embedded archive ---
log_info "Extracting application files..."

ARCHIVE_LINE=$(awk '/^__ARCHIVE_BELOW__/ {print NR + 1; exit 0}' "$0")
if [ -z "$ARCHIVE_LINE" ]; then
    log_error "Corrupted installer: archive marker not found."
    exit 1
fi

TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

tail -n +"$ARCHIVE_LINE" "$0" | tar -xz -C "$TMP_DIR"

# --- Install files ---
if [ -d "$INSTALL_DIR" ]; then
    log_warn "Existing installation found at $INSTALL_DIR"
    log_info "Backing up old installation to ${INSTALL_DIR}.backup.$(date +%s)"
    mv "$INSTALL_DIR" "${INSTALL_DIR}.backup.$(date +%s)"
fi

mkdir -p "$INSTALL_DIR"
cp -r "$TMP_DIR"/* "$INSTALL_DIR/"
log_ok "Files installed to $INSTALL_DIR"

# --- Remove unselected Advanced components ---
if [ "$INSTALL_TYPE" = "2" ]; then
    $INSTALL_PLUGINS || (rm -rf "$INSTALL_DIR/plugins" && log_info "Plugins skipped.")
    $INSTALL_MC_SERVER || (rm -rf "$INSTALL_DIR/server" && log_info "Minecraft Server files skipped.")
    $INSTALL_DOCS || (rm -rf "$INSTALL_DIR/docs" && log_info "Documentation skipped.")

    # Write Java path to config.yaml
    if [ -n "$JAVA_PATH" ]; then
        cat >> "$INSTALL_DIR/config/config.yaml" << EOF

# Java path (set by installer)
java:
  path: "$JAVA_PATH"
EOF
        log_info "Java path written to config."
    fi

    # Write API port to config.yaml
    if [ "$API_PORT" != "29185" ]; then
        cat >> "$INSTALL_DIR/config/config.yaml" << EOF

# API server port (set by installer)
api:
  port: $API_PORT
EOF
        log_info "API port set to $API_PORT."
    fi
fi

# --- Create desktop entry (respects GUI mode) ---
DESKTOP_FILE="/usr/share/applications/tiktok2mc.desktop"
if [ "$GUI_MODE" = "start.bin" ]; then
    cat > "$DESKTOP_FILE" << 'EOF'
[Desktop Entry]
Name=TikTok2Mc
Comment=Start the complete TikTok2Mc stack including API and Minecraft server
Exec=/opt/TikTok2Mc/start.bin
Icon=/opt/TikTok2Mc/core/assets/icon.png
Terminal=true
Type=Application
Categories=Game;Network;
EOF
else
    cat > "$DESKTOP_FILE" << 'EOF'
[Desktop Entry]
Name=TikTok2Mc
Comment=Connect TikTok Live to Minecraft
Exec=/opt/TikTok2Mc/core/gui.bin
Icon=/opt/TikTok2Mc/core/assets/icon.png
Terminal=false
Type=Application
Categories=Game;Network;
EOF
fi

# Also create a "Start Full System" desktop entry (always start.bin)
FULLSYSTEM_FILE="/usr/share/applications/tiktok2mc-fullsystem.desktop"
cat > "$FULLSYSTEM_FILE" << 'EOF'
[Desktop Entry]
Name=TikTok2Mc (Full System)
Comment=Start the complete TikTok2Mc stack including API and Minecraft server
Exec=/opt/TikTok2Mc/start.bin
Icon=/opt/TikTok2Mc/core/assets/icon.png
Terminal=true
Type=Application
Categories=Game;Network;
EOF
log_ok "Desktop entries created."

# --- Symlink (always points to start.bin) ---
if [ -L "$BIN_LINK" ]; then
    rm "$BIN_LINK"
fi
ln -s "$INSTALL_DIR/start.bin" "$BIN_LINK" 2>/dev/null || log_warn "Could not create symlink $BIN_LINK (may need manual setup)"

# --- Autostart (via .desktop autostart) ---
if [ "$INSTALL_TYPE" = "2" ] && [ "$AUTOSTART_ENABLED" = true ]; then
    AUTOSTART_USER_DIR="$HOME/.config/autostart"
    if [ -z "$SUDO_USER" ]; then
        AUTOSTART_USER_DIR=$(eval echo ~${SUDO_USER})/.config/autostart 2>/dev/null || true
    fi
    if [ -n "$AUTOSTART_USER_DIR" ]; then
        mkdir -p "$AUTOSTART_USER_DIR"
        cat > "$AUTOSTART_USER_DIR/tiktok2mc.desktop" << AUTOSTART_EOF
[Desktop Entry]
Type=Application
Name=TikTok2Mc
Exec=/opt/TikTok2Mc/${GUI_MODE}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
AUTOSTART_EOF
        log_ok "Autostart entry created for user ${SUDO_USER:-$USER}."
    fi
fi

# --- Uninstall script ---
cat > "$INSTALL_DIR/uninstall.sh" << 'EOF'
#!/bin/bash
set -e
if [ "$EUID" -ne 0 ]; then
    echo "[ERROR] Run as root (sudo)"
    exit 1
fi
echo "Removing TikTok2Mc..."
rm -rf /opt/TikTok2Mc
rm -f /usr/share/applications/tiktok2mc.desktop
rm -f /usr/share/applications/tiktok2mc-fullsystem.desktop
rm -f /usr/local/bin/tiktok2mc
echo "Removing user autostart entries..."
for f in ~/.config/autostart/tiktok2mc*.desktop; do
    [ -f "$f" ] && rm -f "$f"
done
echo "TikTok2Mc has been uninstalled."
EOF
chmod +x "$INSTALL_DIR/uninstall.sh"
log_ok "Uninstaller created: $INSTALL_DIR/uninstall.sh"

# --- Preserve user config ---
if [ -f "$INSTALL_DIR/config/config.yaml" ]; then
    log_info "User config will be preserved during updates."
fi

# --- Done ---
echo ""
echo "=========================================="
log_ok "Installation complete!"
echo ""
echo "  Start:        $INSTALL_DIR/start.bin"
echo "  Or via terminal: tiktok2mc"
echo "  Uninstall:    sudo $INSTALL_DIR/uninstall.sh"
echo "=========================================="

exit 0

__ARCHIVE_BELOW__
