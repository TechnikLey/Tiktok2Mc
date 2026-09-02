#!/bin/bash
# ============================================================
# TikTok2Mc — Self-Extracting Linux Installer
# ============================================================
# This script extracts the embedded archive and installs
# TikTok2Mc to a per-user location (~/.local/share/TikTok2Mc).
# No root privileges are required, so the Qt GUI runs as a
# normal user (Qt/Chromium refuses to run as root without sandbox).
#
# Usage:
#   chmod +x TikTok2Mc-<version>-Linux-Setup.sh
#   ./TikTok2Mc-<version>-Linux-Setup.sh
# ============================================================

set -e

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$DATA_HOME/TikTok2Mc"
BIN_HOME="${XDG_BIN_HOME:-$HOME/.local/bin}"
BIN_LINK="$BIN_HOME/tiktok2mc"
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

# --- Refuse to run as root ---
# TikTok2Mc is installed per-user so the GUI does not run as root.
if [ "$EUID" -eq 0 ]; then
    log_error "Do not run this installer with sudo/root."
    log_error "TikTok2Mc installs per-user under ~/.local/share."
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
MIN_JAVA=25
if command -v java &> /dev/null; then
    JAVA_VER=$(java -version 2>&1 | awk -F '"' 'NR==1 {print $2}')
    JAVA_MAJOR=$(echo "$JAVA_VER" | awk -F '.' '{print $1}')
    if [ "$JAVA_MAJOR" -ge "$MIN_JAVA" ] 2>/dev/null; then
        log_ok "Java $JAVA_VER found (>= $MIN_JAVA)"
    else
        log_warn "Java $JAVA_VER found, but version $MIN_JAVA+ is required."
        log_warn "Install a newer Java version:"
        log_warn "  Debian/Ubuntu: sudo apt install openjdk-${MIN_JAVA}-jre-headless"
        log_warn "  Fedora:        sudo dnf install java-${MIN_JAVA}-openjdk-headless"
        log_warn "  Arch:          sudo pacman -S jre-openjdk"
    fi
else
    log_warn "Java not found. TikTok2Mc requires Java $MIN_JAVA+."
    log_warn "Install it with one of:"
    log_warn "  Debian/Ubuntu: sudo apt install openjdk-${MIN_JAVA}-jre-headless"
    log_warn "  Fedora:        sudo dnf install java-${MIN_JAVA}-openjdk-headless"
    log_warn "  Arch:          sudo pacman -S jre-openjdk"
fi

# --- Qt xcb-cursor check (Qt6 >= 6.5 requires libxcb-cursor) ---
if command -v ldconfig &> /dev/null; then
    if ! ldconfig -p 2>/dev/null | grep -q libxcb-cursor; then
        log_warn "libxcb-cursor.so.0 not found — the GUI will not start without it."
        log_warn "Install it with:"
        log_warn "  Debian/Ubuntu: sudo apt install libxcb-cursor0"
        log_warn "  Fedora:        sudo dnf install libxcb-cursor"
        log_warn "  Arch:          sudo pacman -S libxcb"
    fi
elif [ -z "$(find /usr/lib /usr/lib64 /usr/lib/x86_64-linux-gnu -name 'libxcb-cursor.so*' 2>/dev/null | head -1)" ]; then
    log_warn "libxcb-cursor.so.0 not found — the GUI will not start without it."
    log_warn "  Debian/Ubuntu: sudo apt install libxcb-cursor0"
    log_warn "  Fedora:        sudo dnf install libxcb-cursor"
    log_warn "  Arch:          sudo pacman -S libxcb"
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
PRESERVE_DIR=""
if [ -d "$INSTALL_DIR" ]; then
    log_warn "Existing installation found at $INSTALL_DIR"
    # Preserve user data (config + data) across updates
    PRESERVE_DIR=$(mktemp -d)
    [ -d "$INSTALL_DIR/config" ] && cp -a "$INSTALL_DIR/config" "$PRESERVE_DIR/config"
    [ -d "$INSTALL_DIR/data" ] && cp -a "$INSTALL_DIR/data" "$PRESERVE_DIR/data"
    log_info "Backing up old installation to ${INSTALL_DIR}.backup.$(date +%s)"
    mv "$INSTALL_DIR" "${INSTALL_DIR}.backup.$(date +%s)"
fi

mkdir -p "$INSTALL_DIR"
cp -r "$TMP_DIR"/* "$INSTALL_DIR/"
log_ok "Files installed to $INSTALL_DIR"

# --- Restore preserved user config/data ---
if [ -n "$PRESERVE_DIR" ]; then
    [ -d "$PRESERVE_DIR/config" ] && cp -a "$PRESERVE_DIR/config" "$INSTALL_DIR/"
    [ -d "$PRESERVE_DIR/data" ] && cp -a "$PRESERVE_DIR/data" "$INSTALL_DIR/"
    rm -rf "$PRESERVE_DIR"
    log_ok "User config and data preserved."
fi

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

# --- Create desktop entries (respects GUI mode) ---
DESKTOP_DIR="$DATA_HOME/applications"
mkdir -p "$DESKTOP_DIR"
DESKTOP_FILE="$DESKTOP_DIR/tiktok2mc.desktop"
if [ "$GUI_MODE" = "start.bin" ]; then
    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=TikTok2Mc
Comment=Start the complete TikTok2Mc stack including API and Minecraft server
Exec=$INSTALL_DIR/start.bin
Terminal=true
Type=Application
Categories=Game;Network;
EOF
else
    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=TikTok2Mc
Comment=Connect TikTok Live to Minecraft
Exec=$INSTALL_DIR/core/gui.bin
Terminal=false
Type=Application
Categories=Game;Network;
EOF
fi

# Also create a "Start Full System" desktop entry (always start.bin)
FULLSYSTEM_FILE="$DESKTOP_DIR/tiktok2mc-fullsystem.desktop"
cat > "$FULLSYSTEM_FILE" << EOF
[Desktop Entry]
Name=TikTok2Mc (Full System)
Comment=Start the complete TikTok2Mc stack including API and Minecraft server
Exec=$INSTALL_DIR/start.bin
Terminal=true
Type=Application
Categories=Game;Network;
EOF
log_ok "Desktop entries created in $DESKTOP_DIR."

# --- Terminal command (per-user, no sudo needed) ---
mkdir -p "$BIN_HOME"
cat > "$BIN_LINK" << 'EOF'
#!/bin/bash
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/TikTok2Mc"

mode="${1:-}"
if [ -n "$mode" ]; then
    shift
fi

case "$mode" in
    start|start.bin)
        TARGET="$INSTALL_DIR/start.bin"
        ;;
    gui|gui.bin)
        TARGET="$INSTALL_DIR/core/gui.bin"
        ;;
    app|app.bin)
        TARGET="$INSTALL_DIR/core/app.bin"
        ;;
    server|server.bin)
        TARGET="$INSTALL_DIR/core/server.bin"
        ;;
    overlay|overlay.bin)
        TARGET="$INSTALL_DIR/core/overlay.bin"
        ;;
    update|update.bin)
        TARGET="$INSTALL_DIR/update.bin"
        ;;
    *)
        echo ""
        echo "TikTok2Mc"
        echo "========="
        echo ""
        echo "Usage: tiktok2mc <mode>"
        echo ""
        echo "Modes:"
        echo "  start.bin    Start the complete stack (API, Minecraft, GUI, overlay)"
        echo "  gui.bin      Open the graphical user interface"
        echo "  app.bin      Start the TikTok-to-Minecraft bridge"
        echo "  server.bin   Start the Minecraft server"
        echo "  overlay.bin  Start the overlay"
        echo "  update.bin   Run the updater"
        echo ""
        echo "Example: tiktok2mc start.bin"
        echo "         tiktok2mc gui.bin"
        exit 1
        ;;
esac

if [ ! -f "$TARGET" ]; then
    echo "[ERROR] Not found: $TARGET" >&2
    echo "Re-run the installer or check the installation directory." >&2
    exit 1
fi

exec "$TARGET" "$@"
EOF
chmod +x "$BIN_LINK"
log_ok "Terminal command created: $BIN_LINK (e.g. 'tiktok2mc start.bin')"

case ":$PATH:" in
    *":$BIN_HOME:"*) : ;;
    *)
        log_warn "$BIN_HOME is not on your PATH."
        log_warn "Add it to your shell profile, e.g.: echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
        ;;
esac

# --- Autostart (via .desktop autostart) ---
if [ "$INSTALL_TYPE" = "2" ] && [ "$AUTOSTART_ENABLED" = true ]; then
    AUTOSTART_USER_DIR="$HOME/.config/autostart"
    mkdir -p "$AUTOSTART_USER_DIR"
    cat > "$AUTOSTART_USER_DIR/tiktok2mc.desktop" << AUTOSTART_EOF
[Desktop Entry]
Type=Application
Name=TikTok2Mc
Exec=$INSTALL_DIR/${GUI_MODE}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
AUTOSTART_EOF
    log_ok "Autostart entry created for user $USER."
fi

# --- Uninstall script ---
cat > "$INSTALL_DIR/uninstall.sh" << 'EOF'
#!/bin/bash
set -e
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/TikTok2Mc"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_HOME="${XDG_BIN_HOME:-$HOME/.local/bin}"
echo "Removing TikTok2Mc..."
read -p "Are you sure you want to uninstall TikTok2Mc? (y/n) [n]: " confirm
confirm=${confirm:-n}
if [ "$confirm" != "Y" ] && [ "$confirm" != "y" ]; then
    echo "Uninstall cancelled."
    exit 1
fi
rm -rf "$INSTALL_DIR"
rm -f "$DATA_HOME/applications/tiktok2mc.desktop"
rm -f "$DATA_HOME/applications/tiktok2mc-fullsystem.desktop"
rm -f "$BIN_HOME/tiktok2mc"
echo "Removing user autostart entries..."
for f in "$HOME/.config/autostart"/tiktok2mc*.desktop; do
    [ -f "$f" ] && rm -f "$f"
done
echo "TikTok2Mc has been uninstalled."
EOF
chmod +x "$INSTALL_DIR/uninstall.sh"
log_ok "Uninstaller created: $INSTALL_DIR/uninstall.sh"

# --- Done ---
echo ""
echo "=========================================="
log_ok "Installation complete!"
echo ""
echo "  Start:        tiktok2mc start.bin"
echo "  GUI:          tiktok2mc gui.bin"
echo "  Uninstall:    $INSTALL_DIR/uninstall.sh"
echo "=========================================="

exit 0

__ARCHIVE_BELOW__
