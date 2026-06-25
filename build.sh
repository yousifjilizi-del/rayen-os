#!/usr/bin/env bash
# Rayen OS Phase 1 — Bare ISO Builder
set -euo pipefail

RAYEN_VERSION="${RAYEN_VERSION:-1.0.0-rc1}"
ARCH="${ARCH:-amd64}"
MIRROR="${MIRROR:-http://archive.ubuntu.com/ubuntu}"
DISTRIBUTION="${DISTRIBUTION:-noble}"
OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)/output}"

info()  { echo -e "\033[1;34m[INFO]\033[0m $*"; }
ok()    { echo -e "\033[1;32m[OK]\033[0m   $*"; }
error() { echo -e "\033[1;31m[ERROR]\033[0m $*"; exit 1; }

check_root() { [[ $EUID -eq 0 ]] || error "Run as root: sudo ./build.sh"; }

check_deps() {
    local deps=("lb" "debootstrap" "xorriso" "mksquashfs")
    for dep in "${deps[@]}"; do
        command -v "$dep" &>/dev/null || error "Missing: $dep"
    done
    ok "Dependencies OK"
}

setup_config() {
    info "Configuring live-build..."
    mkdir -p "$OUTPUT_DIR"
    lb config \
        --distribution "$DISTRIBUTION" \
        --architectures "$ARCH" \
        --mirror-bootstrap "$MIRROR" \
        --mirror-chroot "$MIRROR" \
        --archive-areas "main universe multiverse restricted" \
        --bootappend-live "boot=live components quiet splash" \
        --bootappend-install "quiet splash" \
        --iso-application "Rayen OS ${RAYEN_VERSION}" \
        --iso-publisher "Rayen OS" \
        --iso-volume "Rayen OS ${RAYEN_VERSION}" \
        --memtest none \
        --bootloader "grub-efi grub-pc" \
        "${@}"
    ok "Config done"
}

build_image() {
    info "Building image (this takes a while)..."
    lb build --force 2>&1 | tee build.log
    ok "Build complete"
}

package_iso() {
    info "Packaging ISO..."
    mkdir -p "$OUTPUT_DIR"
    local src="live-image-${ARCH}.hybrid.iso"
    local dst="${OUTPUT_DIR}/rayen-os-${RAYEN_VERSION}-${ARCH}.iso"
    [[ -f "$src" ]] || src="${OUTPUT_DIR}/../${src}"
    [[ -f "$src" ]] || error "No ISO found after build"
    cp "$src" "$dst"
    sha256sum "$dst" > "${dst}.sha256"
    ok "ISO: $dst"
    ok "SHA256: ${dst}.sha256"
}

clean() {
    info "Cleaning..."
    lb clean --purge 2>/dev/null || true
    rm -rf build.log tmp/
    ok "Clean"
}

case "${1:-all}" in
    config) check_root; check_deps; setup_config "${@:2}" ;;
    build)  check_root; check_deps; build_image ;;
    iso)    package_iso ;;
    clean)  check_root; clean ;;
    all)
        check_root
        check_deps
        setup_config "${@:2}"
        build_image
        package_iso
        ;;
    *) echo "Usage: $0 {config|build|iso|clean|all}"; exit 1 ;;
esac
