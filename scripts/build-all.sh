#!/usr/bin/env bash
# scripts/build-all.sh - Build all AutoType release packages
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist"
VERSION="1.0.0"

echo "=== AutoType v${VERSION} Release Build Pipeline ==="
mkdir -p "${DIST_DIR}"

# Detect container runtime
CONTAINER_CMD=""
if command -v podman &>/dev/null; then
    CONTAINER_CMD="podman"
elif command -v docker &>/dev/null; then
    CONTAINER_CMD="docker"
fi

echo "Working directory: ${REPO_ROOT}"
echo "Distribution directory: ${DIST_DIR}"

# 1. Build .deb
echo "--- Building Debian package (autotype_${VERSION}_amd64.deb) ---"
BUILD_DEB_DIR="$(mktemp -d /tmp/autotype-deb.XXXXXX)"
mkdir -p "${BUILD_DEB_DIR}/DEBIAN"
mkdir -p "${BUILD_DEB_DIR}/usr/bin"
mkdir -p "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/autotype"
mkdir -p "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/audio"
mkdir -p "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/context"
mkdir -p "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/desktop"
mkdir -p "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/llm"
mkdir -p "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/stt"
mkdir -p "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/ui"
mkdir -p "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/utils"
mkdir -p "${BUILD_DEB_DIR}/usr/share/applications"
mkdir -p "${BUILD_DEB_DIR}/usr/share/metainfo"
mkdir -p "${BUILD_DEB_DIR}/usr/share/icons/hicolor/scalable/apps"
mkdir -p "${BUILD_DEB_DIR}/usr/share/doc/autotype"

# Copy python code (excluding __pycache__ and bytecode)
rsync -a --exclude='__pycache__' --exclude='*.pyc' "${REPO_ROOT}/autotype/" "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/autotype/"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "${REPO_ROOT}/audio/" "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/audio/"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "${REPO_ROOT}/context/" "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/context/"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "${REPO_ROOT}/desktop/" "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/desktop/"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "${REPO_ROOT}/llm/" "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/llm/"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "${REPO_ROOT}/stt/" "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/stt/"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "${REPO_ROOT}/ui/" "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/ui/"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "${REPO_ROOT}/utils/" "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/utils/"

# Copy root entry scripts if any
cp "${REPO_ROOT}/app.py" "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/"
cp "${REPO_ROOT}/config.py" "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/"
cp "${REPO_ROOT}/settings_gui.py" "${BUILD_DEB_DIR}/usr/lib/python3/dist-packages/"

# Create /usr/bin/autotype wrapper
cat <<'EOF' > "${BUILD_DEB_DIR}/usr/bin/autotype"
#!/usr/bin/env python3
import sys
from autotype.cli import main
if __name__ == "__main__":
    sys.exit(main())
EOF
chmod 755 "${BUILD_DEB_DIR}/usr/bin/autotype"

# Copy desktop and metainfo
cp "${REPO_ROOT}/io.github.premtechworks.AutoType.desktop" "${BUILD_DEB_DIR}/usr/share/applications/"
cp "${REPO_ROOT}/io.github.premtechworks.AutoType.metainfo.xml" "${BUILD_DEB_DIR}/usr/share/metainfo/"
cp "${REPO_ROOT}/icons/hicolor/scalable/apps/io.github.premtechworks.AutoType.svg" "${BUILD_DEB_DIR}/usr/share/icons/hicolor/scalable/apps/"
cp "${REPO_ROOT}/LICENSE" "${BUILD_DEB_DIR}/usr/share/doc/autotype/copyright"

# Create DEBIAN/control
cat <<EOF > "${BUILD_DEB_DIR}/DEBIAN/control"
Package: autotype
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Prem kumar Gara <premtechworks@gmail.com>
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, libportaudio2
Recommends: xdotool, libnotify-bin
Suggests: pulseaudio-utils, xclip
Description: Voice-typing daemon for Linux Mint XFCE on X11
 AutoType is an open-source voice typing daemon and assistant designed for Linux
 Mint XFCE and other X11 desktop environments.
EOF

dpkg-deb --build --root-owner-group "${BUILD_DEB_DIR}" "${DIST_DIR}/autotype_${VERSION}_amd64.deb"
rm -rf "${BUILD_DEB_DIR}"
echo "Debian package created: ${DIST_DIR}/autotype_${VERSION}_amd64.deb"

# 2. Build .rpm
echo "--- Building RPM package (autotype-${VERSION}-1.x86_64.rpm) ---"
if command -v rpmbuild &>/dev/null; then
    rpmbuild -bb autotype.spec --define "_sourcedir ${REPO_ROOT}" --define "_rpmdir ${DIST_DIR}"
elif [ -n "${CONTAINER_CMD}" ]; then
    "${CONTAINER_CMD}" run --rm -v "${REPO_ROOT}:/src" -w /src fedora:latest bash -c \
        "dnf install -y rpm-build python3-devel && rpmbuild -bb autotype.spec && cp ~/rpmbuild/RPMS/*/*.rpm /src/dist/"
else
    echo "Warning: Neither rpmbuild nor container runtime found. Checking nfpm..."
    if command -v nfpm &>/dev/null; then
        nfpm package --packager rpm --target "${DIST_DIR}/autotype-${VERSION}-1.x86_64.rpm"
    else
        echo "RPM build skipped or requires container runtime."
    fi
fi

# 3. Build AppImage
echo "--- Building AppImage (AutoType-${VERSION}-x86_64.AppImage) ---"
if command -v appimage-builder &>/dev/null; then
    appimage-builder --recipe appimage-builder.yml
    mv "AutoType-${VERSION}-x86_64.AppImage" "${DIST_DIR}/" || true
else
    echo "AppImage build requires appimage-builder."
fi

# 4. Build Flatpak
echo "--- Building Flatpak bundle (AutoType-${VERSION}.flatpak) ---"
if command -v flatpak-builder &>/dev/null; then
    flatpak-builder --force-clean --repo="${REPO_ROOT}/repo" "${REPO_ROOT}/builddir" "${REPO_ROOT}/io.github.premtechworks.AutoType.json"
    flatpak build-bundle "${REPO_ROOT}/repo" "${DIST_DIR}/AutoType-${VERSION}.flatpak" io.github.premtechworks.AutoType
else
    echo "Flatpak build requires flatpak-builder."
fi

# 5. Checksums
echo "--- Generating SHA256SUMS ---"
cd "${DIST_DIR}"
if compgen -G "*" > /dev/null; then
    sha256sum -- * | grep -v "SHA256SUMS" > SHA256SUMS.tmp 2>/dev/null || true
    mv SHA256SUMS.tmp SHA256SUMS || true
fi

echo "=== Build finished ==="
ls -lh "${DIST_DIR}"
