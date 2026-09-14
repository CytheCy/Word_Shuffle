#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VERSION="${1:-1.0.0}"
if [[ ! "$VERSION" =~ ^[0-9]+([.][0-9]+)*([~-][A-Za-z0-9.]+)?$ ]]; then
    echo "Invalid version: $VERSION" >&2
    exit 1
fi
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|aarch64) ;;
    *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
esac

BUILD="$ROOT/build/packages"
DIST="$ROOT/dist"
STAGE="$BUILD/stage"
APP_ID="io.github.CytheCy.WordShuffle"

for command in ar rpmbuild tar xz; do
    command -v "$command" >/dev/null || {
        echo "Missing required command: $command" >&2
        exit 1
    }
done

rm -rf "$BUILD"
mkdir -p "$BUILD" "$DIST" "$STAGE/usr/bin" \
    "$STAGE/usr/lib/word-shuffle" \
    "$STAGE/usr/share/applications" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps" \
    "$STAGE/usr/share/metainfo" \
    "$STAGE/usr/share/mime/packages" \
    "$STAGE/usr/share/licenses/word-shuffle"

install -m 0755 "$ROOT/packaging/word-shuffle" "$STAGE/usr/bin/word-shuffle"
install -m 0644 "$ROOT/word_shuffle.py" "$STAGE/usr/lib/word-shuffle/word_shuffle.py"
install -m 0644 "$ROOT/word-shuffle.svg" "$STAGE/usr/lib/word-shuffle/word-shuffle.svg"
install -m 0644 "$ROOT/word-shuffle.svg" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
install -m 0644 "$ROOT/packaging/$APP_ID.desktop" \
    "$STAGE/usr/share/applications/$APP_ID.desktop"
install -m 0644 "$ROOT/packaging/$APP_ID.metainfo.xml" \
    "$STAGE/usr/share/metainfo/$APP_ID.metainfo.xml"
sed -i "s/version=\"1.0.0\"/version=\"$VERSION\"/" \
    "$STAGE/usr/share/metainfo/$APP_ID.metainfo.xml"
install -m 0644 "$ROOT/word-shuffle-mime.xml" \
    "$STAGE/usr/share/mime/packages/word-shuffle.xml"
install -m 0644 "$ROOT/LICENSE" \
    "$STAGE/usr/share/licenses/word-shuffle/LICENSE"

build_deb() {
    local deb_root="$BUILD/deb-root"
    local control="$deb_root/DEBIAN/control"
    rm -rf "$deb_root"
    mkdir -p "$deb_root/DEBIAN"
    cp -a "$STAGE/." "$deb_root/"
    cat > "$control" <<EOF
Package: word-shuffle
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Maintainer: CyAtWork <portercy@gmail.com>
Depends: python3, python3-pyside6.qtcore, python3-pyside6.qtgui, python3-pyside6.qtwidgets
Homepage: https://github.com/CytheCy/Word_Shuffle
Description: Shuffle word and phrase lists into clickable blocks
 Word Shuffle displays non-empty lines from .shfl files as shuffled blocks.
 Control-clicking a block removes it from the file and copies it to the clipboard.
EOF
    chmod 0755 "$deb_root/DEBIAN"
    chmod 0644 "$control"

    local deb_work="$BUILD/deb-work"
    rm -rf "$deb_work"
    mkdir -p "$deb_work"
    printf '2.0\n' > "$deb_work/debian-binary"
    tar -C "$deb_root/DEBIAN" --owner=0 --group=0 -cJf "$deb_work/control.tar.xz" .
    tar -C "$deb_root" --exclude=DEBIAN --owner=0 --group=0 -cJf "$deb_work/data.tar.xz" .
    (
        cd "$deb_work"
        ar rcs "$DIST/word-shuffle_${VERSION}_all.deb" \
            debian-binary control.tar.xz data.tar.xz
    )
}

build_rpm() {
    local rpm_top="$BUILD/rpmbuild"
    mkdir -p "$rpm_top"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS,tmp}
    tar -C "$STAGE" -czf "$rpm_top/SOURCES/word-shuffle-$VERSION.tar.gz" .
    cat > "$rpm_top/SPECS/word-shuffle.spec" <<EOF
Name:           word-shuffle
Version:        $VERSION
Release:        1
Summary:        Shuffle word and phrase lists into clickable blocks
License:        MIT
URL:            https://github.com/CytheCy/Word_Shuffle
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
Requires:       python3
Requires:       python3-pyside6

%description
Word Shuffle displays non-empty lines from .shfl files as shuffled blocks.
Control-clicking a block removes it from the file and copies it to the clipboard.

%prep

%build

%install
mkdir -p %{buildroot}
tar -xzf %{SOURCE0} -C %{buildroot}

%files
/usr/bin/word-shuffle
/usr/lib/word-shuffle/
/usr/share/applications/$APP_ID.desktop
/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg
/usr/share/metainfo/$APP_ID.metainfo.xml
/usr/share/mime/packages/word-shuffle.xml
/usr/share/licenses/word-shuffle/LICENSE
EOF
    rpmbuild --define "_topdir $rpm_top" --define "_tmppath $rpm_top/tmp" \
        -bb "$rpm_top/SPECS/word-shuffle.spec"
    find "$rpm_top/RPMS" -type f -name '*.rpm' -exec cp {} "$DIST/" \;
}

build_appimage() {
    local pyinstaller="$ROOT/.venv/bin/pyinstaller"
    local appimagetool="${APPIMAGETOOL:-$ROOT/.venv/bin/appimagetool}"
    if [[ ! -x "$pyinstaller" ]]; then
        echo "PyInstaller is missing. Run: python3 -m venv --system-site-packages .venv" >&2
        echo "Then run: .venv/bin/pip install pyinstaller" >&2
        exit 1
    fi
    if [[ ! -x "$appimagetool" ]]; then
        echo "appimagetool is missing; set APPIMAGETOOL to its path" >&2
        exit 1
    fi

    "$pyinstaller" --noconfirm --clean --onedir --windowed \
        --name word-shuffle \
        --add-data "$ROOT/word-shuffle.svg:." \
        --distpath "$BUILD/pyinstaller-dist" \
        --workpath "$BUILD/pyinstaller-work" \
        --specpath "$BUILD" \
        "$ROOT/word_shuffle.py"

    local appdir="$BUILD/WordShuffle.AppDir"
    mkdir -p "$appdir/usr/lib/word-shuffle" "$appdir/usr/bin"
    cp -a "$BUILD/pyinstaller-dist/word-shuffle/." "$appdir/usr/lib/word-shuffle/"
    rm -f "$appdir/usr/lib/word-shuffle/_internal/PySide6/Qt/plugins/imageformats/libqtiff.so"
    install -m 0755 "$ROOT/packaging/AppRun" "$appdir/AppRun"
    ln -s ../lib/word-shuffle/word-shuffle "$appdir/usr/bin/word-shuffle"
    mkdir -p "$appdir/usr/share/applications" \
        "$appdir/usr/share/icons/hicolor/scalable/apps" \
        "$appdir/usr/share/metainfo"
    install -m 0644 "$ROOT/packaging/$APP_ID.desktop" "$appdir/$APP_ID.desktop"
    install -m 0644 "$ROOT/packaging/$APP_ID.desktop" \
        "$appdir/usr/share/applications/$APP_ID.desktop"
    install -m 0644 "$ROOT/word-shuffle.svg" "$appdir/$APP_ID.svg"
    install -m 0644 "$ROOT/word-shuffle.svg" \
        "$appdir/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
    install -m 0644 "$STAGE/usr/share/metainfo/$APP_ID.metainfo.xml" \
        "$appdir/usr/share/metainfo/$APP_ID.appdata.xml"

    ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$appimagetool" --no-appstream "$appdir" \
        "$DIST/Word_Shuffle-${VERSION}-${ARCH}.AppImage"
}

build_deb
build_rpm
build_appimage

echo
echo "Packages created in $DIST:"
find "$DIST" -maxdepth 1 -type f \( -name '*.deb' -o -name '*.rpm' -o -name '*.AppImage' \) \
    -printf '  %f (%k KiB)\n' | sort
