#!/bin/sh
# Installa/rimuove la voce di menu (Internet > gui-gftp) e l'icona per l'utente corrente. Uso: install.sh [--remove]
set -e
D="$(cd "$(dirname "$0")" && pwd)"
APP="${XDG_DATA_HOME:-$HOME/.local/share}"
if [ "$1" = "--remove" ]; then
    rm -f "$APP/applications/gui-gftp.desktop" "$APP/icons/hicolor/scalable/apps/gui-gftp.svg"
else
    mkdir -p "$APP/applications" "$APP/icons/hicolor/scalable/apps"
    cp "$D/gui-gftp.svg" "$APP/icons/hicolor/scalable/apps/gui-gftp.svg"
    cat > "$APP/applications/gui-gftp.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=gui-gftp
Comment=Client FTP/FTPS/SFTP a due pannelli
Exec=python3 $D/gui_gftp.py
Icon=gui-gftp
Terminal=false
Categories=Network;FileTransfer;
StartupWMClass=gui-gftp
EOF
fi
update-desktop-database "$APP/applications" 2>/dev/null || true
gtk-update-icon-cache -f -t "$APP/icons/hicolor" 2>/dev/null || true
