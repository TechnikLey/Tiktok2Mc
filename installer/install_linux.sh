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

# The archive starts after the __ARCHIVE_BELOW__ marker
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

# --- Create desktop entry ---
DESKTOP_FILE="/usr/share/applications/tiktok2mc.desktop"
cat > "$DESKTOP_FILE" << 'EOF'
[Desktop Entry]
Name=TikTok2Mc
Comment=Connect TikTok Live to Minecraft
Exec=/opt/TikTok2Mc/start.bin
Icon=/opt/TikTok2Mc/core/assets/icon.png
Terminal=false
Type=Application
Categories=Game;Network;
EOF
log_ok "Desktop entry created: $DESKTOP_FILE"

# --- Symlink ---
if [ -L "$BIN_LINK" ]; then
    rm "$BIN_LINK"
fi
ln -s "$INSTALL_DIR/start.bin" "$BIN_LINK" 2>/dev/null || log_warn "Could not create symlink $BIN_LINK (may need manual setup)"

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
rm -f /usr/local/bin/tiktok2mc
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
