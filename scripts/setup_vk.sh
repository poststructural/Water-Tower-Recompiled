#!/usr/bin/env bash
# One-time setup for the Vulkan build (vk/CMakeLists.txt) on Windows.
#
#   scripts/setup_vk.sh
#
# 1. ngbrecomp's xboxrecomp fork: its third-party sources, and this
#    project's patches to it (patches/ngbrecomp-*.patch).
# 2. llvm-mingw and the MSYS2 CLANG64 packages the fork links (SDL2, glib,
#    glslang, SPIRV-Tools, the Vulkan loader), unpacked into work/windeps.
#    The package list is ngbrecomp's own (packaging/windows/deps.txt).
#
# Then:
#   TK=tools/ngbrecomp/xboxrecomp scripts/regen.sh
#   cmake -S vk -B build-vk -G Ninja \
#       -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/windows-llvm-mingw.cmake
#   ninja -C build-vk
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NGB="$ROOT/tools/ngbrecomp"
DEPS="${ANI_WIN_DEPS:-$ROOT/work/windeps}"
LLVM=llvm-mingw-20260922-ucrt-x86_64
MSYS=https://repo.msys2.org/mingw/clang64

git -C "$ROOT" submodule update --init tools/ngbrecomp
bash "$NGB/xboxrecomp/third_party/fetch.sh"
for p in "$ROOT"/patches/ngbrecomp-*.patch; do
    if git -C "$NGB" apply --check "$p" 2>/dev/null; then
        git -C "$NGB" apply "$p" && echo "applied $(basename "$p")"
    else
        echo "skipped $(basename "$p") (already applied?)"
    fi
done

mkdir -p "$DEPS/pkgs" "$DEPS/sysroot"
if [ ! -x "$DEPS/$LLVM/bin/clang.exe" ]; then
    curl -fL -o "$DEPS/$LLVM.zip" \
        "https://github.com/mstorsjo/llvm-mingw/releases/download/20260922/$LLVM.zip"
    (cd "$DEPS" && unzip -q "$LLVM.zip")
fi
# bsdtar reads .zst; Windows 10+ ships one as tar.exe.
TAR=tar
[ -x /c/Windows/System32/tar.exe ] && TAR=/c/Windows/System32/tar.exe
for p in $(grep -v '^#' "$NGB/packaging/windows/deps.txt" | grep .); do
    [ -s "$DEPS/pkgs/$p" ] || curl -fL -o "$DEPS/pkgs/$p" "$MSYS/$p"
    "$TAR" -xf "$DEPS/pkgs/$p" -C "$DEPS/sysroot" clang64
done
echo "Windows dependencies in $DEPS"
