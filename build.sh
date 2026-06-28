#!/usr/bin/env bash
# Rayen OS Phase 1 — Bare ISO Builder
set -uo pipefail

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
    local deps=("lb" "debootstrap" "xorriso" "mksquashfs" "grub-mkrescue")
    local missing=()
    for dep in "${deps[@]}"; do
        command -v "$dep" &>/dev/null || missing+=("$dep")
    done
    [[ ${#missing[@]} -eq 0 ]] || error "Missing: ${missing[*]}"
    ok "Dependencies OK"
}

setup_config() {
    info "Configuring live-build..."
    mkdir -p "$OUTPUT_DIR"
    lb clean --purge 2>/dev/null || true
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
        --bootloader "grub2" \
        "${@}"
    ok "Config done"
}

# Replace lb_binary_iso with a no-op — we create the ISO ourselves via grub-mkrescue
patch_lb_binary_iso() {
    local f
    for f in /usr/lib/live/build/lb_binary_iso /usr/lib/live/build/lb_binary_iso.sh; do
        [ -f "$f" ] || continue
        info "Replacing $f with no-op (ISO will be built by grub-mkrescue)"
        cat > "$f" << 'NOOP'
#!/bin/sh
. /usr/lib/live/build.sh
Create_stagefile .build/binary_iso
NOOP
        chmod +x "$f"
        ok "Replaced $f"
    done
}

build_image() {
    info "Building image (this takes a while)..."
    patch_lb_binary_iso
    lb build 2>&1 | tee build.log || true

    # binary/ directory should exist after lb build (lb_binary_iso was a no-op)
    if [ ! -d "binary" ]; then
        # Maybe it's in chroot/binary? Check various locations
        if [ -d "chroot/binary" ]; then
            info "Found binary/ inside chroot/, moving out..."
            mv chroot/binary .
        elif [ -d ".build/binary" ]; then
            info "Found binary/ in .build/"
            mv .build/binary .
        else
            error "binary/ directory not found after lb build"
        fi
    fi

    # Create the bootable ISO with grub-mkrescue
    local iso_name="binary.hybrid.iso"
    info "Creating bootable ISO with grub-mkrescue..."
    grub-mkrescue -o "$iso_name" binary/ 2>&1 | tee -a build.log || true

    if [ ! -f "$iso_name" ]; then
        info "grub-mkrescue failed, trying xorriso directly..."
        xorriso -as mkisofs \
            -r -V "Rayen OS ${RAYEN_VERSION}" \
            -J -l -cache-inodes \
            -b boot/grub/grub_eltorito -no-emul-boot -boot-load-size 4 -boot-info-table \
            -o "$iso_name" binary/
    fi

    local iso
    iso=$(find . -maxdepth 3 -name "*.iso" -type f 2>/dev/null | head -1)
    if [ -z "$iso" ]; then
        error "No ISO file found after build"
    fi

    # Run isohybrid for USB boot compatibility
    if command -v isohybrid &>/dev/null; then
        info "Running isohybrid on $iso..."
        isohybrid "$iso" 2>/dev/null || info "isohybrid warning (non-fatal)"
    fi

    ok "Build complete — ISO: $iso"
}

package_iso() {
    info "Packaging ISO..."
    mkdir -p "$OUTPUT_DIR"
    local src
    src=$(find . -maxdepth 3 -name "*.iso" -type f 2>/dev/null | head -1)
    [ -n "$src" ] || error "No ISO found to package"
    local dst="${OUTPUT_DIR}/rayen-os-${RAYEN_VERSION}-${ARCH}.iso"
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
