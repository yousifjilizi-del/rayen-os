#!/usr/bin/env bash
# Rayen OS Phase 1 — Bare ISO Builder
set -uo pipefail

RAYEN_VERSION="${RAYEN_VERSION:-1.0.0-rc1}"
ARCH="${ARCH:-amd64}"
MIRROR="${MIRROR:-http://archive.ubuntu.com/ubuntu}"
DISTRIBUTION="${DISTRIBUTION:-noble}"
OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)/output}"
# Set to 0 to skip downloading the offline model (smaller ISO, no offline AI)
RAYEN_DOWNLOAD_MODEL="${RAYEN_DOWNLOAD_MODEL:-1}"
MODEL_GGUF="qwen2.5-0.5b-instruct-q4_k_m.gguf"
MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/${MODEL_GGUF}"
LLAMA_ZIP_URL="https://github.com/ggml-org/llama.cpp/releases/download/b3920/llama-b3920-bin-ubuntu-x64.zip"
# Set to 0 to skip downloading the Thorium browser (.deb)
RAYEN_DOWNLOAD_BROWSER="${RAYEN_DOWNLOAD_BROWSER:-1}"
THORIUM_DEB_VERSION="138.0.7204.303"
THORIUM_DEB_ARCH="SSE3"
THORIUM_DEB_URL="https://github.com/Alex313031/thorium/releases/download/M${THORIUM_DEB_VERSION}/thorium-browser_${THORIUM_DEB_VERSION}_${THORIUM_DEB_ARCH}.deb"

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

# Download llama.cpp binary + small GGUF model for offline AI (Phase 2)
download_offline_model() {
    local dst="config/includes.chroot/usr/share/rayen-ai"
    mkdir -p "$dst/models"
    local llama_bin="$dst/llama-cli"
    local model_file="$dst/models/$MODEL_GGUF"

    if [ "${RAYEN_DOWNLOAD_MODEL}" != "1" ]; then
        info "Skipping offline model download (RAYEN_DOWNLOAD_MODEL=0)"
        return 0
    fi

    # Download GGUF model
    if [ ! -f "$model_file" ]; then
        info "Downloading offline model ($MODEL_GGUF, ~450MB)..."
        curl -L --fail --retry 3 -o "$model_file" "$MODEL_URL" || {
            info "Model download failed; offline AI unavailable"
            rm -f "$model_file"
            return 0
        }
        ok "Model downloaded"
    fi

    # Download and extract llama-cli
    if [ ! -f "$llama_bin" ]; then
        info "Downloading llama.cpp binary..."
        local tmpzip
        tmpzip=$(mktemp --suffix=.zip)
        curl -L --fail --retry 3 -o "$tmpzip" "$LLAMA_ZIP_URL" || {
            info "llama.cpp download failed; offline AI unavailable"
            rm -f "$tmpzip"
            return 0
        }
        (cd "$dst" && unzip -o -j "$tmpzip" "*llama-cli*" 2>/dev/null) || true
        rm -f "$tmpzip"
        chmod +x "$llama_bin" 2>/dev/null || true
        ok "llama-cli installed"
    fi
    return 0
}

# Download Thorium browser .deb into config/packages (auto-installed by live-build)
download_browser() {
    local dst_dir="config/packages"
    mkdir -p "$dst_dir"
    local deb_file="$dst_dir/thorium-browser_${THORIUM_DEB_VERSION}_${THORIUM_DEB_ARCH}.deb"

    if [ "${RAYEN_DOWNLOAD_BROWSER}" != "1" ]; then
        info "Skipping browser download (RAYEN_DOWNLOAD_BROWSER=0)"
        return 0
    fi
    if [ -f "$deb_file" ]; then
        ok "Thorium deb already present"
        return 0
    fi
    info "Downloading Thorium browser (${THORIUM_DEB_VERSION}, ~160MB)..."
    curl -L --fail --retry 3 -o "$deb_file" "$THORIUM_DEB_URL" || {
        info "Thorium download failed; no browser in image"
        rm -f "$deb_file"
        return 0
    }
    ok "Thorium browser downloaded"
    return 0
}

setup_config() {
    info "Configuring live-build..."
    mkdir -p "$OUTPUT_DIR"

    # Copy Rayen AI sources into chroot includes (installed by 04-ai-install.chroot)
    local ai_dst="config/includes.chroot/usr/share/rayen-ai-src"
    rm -rf "$ai_dst"
    mkdir -p "$ai_dst"
    cp -r ai/rayen_ai ai/rayen-ai ai/install.sh ai/config "$ai_dst/"
    ok "AI sources staged into chroot includes"

    # Inject Qwen API key from secret/env (keeps key out of public repo)
    if [ -n "${QWEN_API_KEY:-}" ] && [ -f "$ai_dst/config/config.json" ]; then
        sed -i "s|PASTE_QWEN_API_KEY_HERE|${QWEN_API_KEY}|" "$ai_dst/config/config.json"
        info "Qwen API key injected from environment"
    else
        info "QWEN_API_KEY not set; AI will fall back to offline mode"
    fi

    # Stage offline model + llama.cpp for offline AI
    download_offline_model

    # Stage Thorium browser .deb (auto-installed from config/packages)
    download_browser

    lb clean --purge 2>/dev/null || true
    lb config \
        --distribution "$DISTRIBUTION" \
        --architectures "$ARCH" \
        --mirror-bootstrap "$MIRROR" \
        --mirror-chroot "$MIRROR" \
        --archive-areas "main universe multiverse restricted" \
        --bootappend-live "boot=casper nomodeset" \
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

# Generate the live GRUB menu with the exact kernel/initrd names from the build,
# so the boot entries never depend on GRUB wildcard expansion.
generate_grub_cfg() {
    local binary_dir="$1"
    local kern initrd
    kern=$(find "$binary_dir/casper" -maxdepth 1 -name 'vmlinuz-*' -printf '%f\n' 2>/dev/null | head -n1)
    initrd=$(find "$binary_dir/casper" -maxdepth 1 -name 'initrd.img-*' -printf '%f\n' 2>/dev/null | head -n1)
    if [ -z "$kern" ] || [ -z "$initrd" ]; then
        error "Could not find kernel/initrd under $binary_dir/casper"
    fi
    cat > "$binary_dir/boot/grub/grub.cfg" << EOF
set default=0
set timeout=10

insmod all_video
insmod gfxterm
insmod png
insmod iso9660

set gfxmode=1024x768
terminal_output gfxterm

set color_normal=white/black
set color_highlight=white/dark-blue

background_image /boot/grub/grub-bg.png

search --no-floppy --set=root --file /casper/filesystem.squashfs

menuentry "Try Rayen OS" {
  linux /casper/${kern} boot=casper nomodeset
  initrd /casper/${initrd}
}
menuentry "Try Rayen OS (safe graphics)" {
  linux /casper/${kern} boot=casper nomodeset quiet splash
  initrd /casper/${initrd}
}
EOF
    ok "Generated grub.cfg (kernel: ${kern})"
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

    # Generate the live GRUB menu with exact kernel filenames (before grub-mkrescue)
    generate_grub_cfg "binary"

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
