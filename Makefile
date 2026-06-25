.PHONY: all clean build iso help check-deps test-vm

all: build

help:
	@echo "Rayen OS Phase 1 Build"
	@echo "======================"
	@echo "make build       - Build the ISO image"
	@echo "make clean       - Clean build artifacts"
	@echo "make iso         - Package ISO"
	@echo "make test-vm     - Launch in VirtualBox (if VBoxManage exists)"
	@echo "make docker      - Build inside Docker container"

check-deps:
	@echo "Checking build dependencies..."
	@command -v lb >/dev/null 2>&1 || { echo "ERROR: live-build not installed"; exit 1; }
	@command -v debootstrap >/dev/null 2>&1 || { echo "ERROR: debootstrap not installed"; exit 1; }
	@command -v xorriso >/dev/null 2>&1 || { echo "ERROR: xorriso not installed"; exit 1; }
	@command -v mksquashfs >/dev/null 2>&1 || { echo "ERROR: squashfs-tools not installed"; exit 1; }
	@echo "All dependencies found."

build: check-deps
	@echo "Building Rayen OS ISO..."
	@sudo ./build.sh all

clean:
	@echo "Cleaning..."
	@sudo lb clean --purge 2>/dev/null || true
	@rm -rf output/ build.log *.iso *.sha256 tmp/
	@echo "Clean."

iso:
	@./build.sh iso

test-vm:
	@echo "Launching in VirtualBox..."
	@VBoxManage startvm "rayen-os-test" 2>/dev/null || \
	 echo "Create VM: VBoxManage createvm --name rayen-os-test --ostype Ubuntu_64 --register && \
VBoxManage modifyvm rayen-os-test --memory 4096 --vram 128 --graphicscontroller vmsvga && \
VBoxManage storagectl rayen-os-test --name SATA --add sata --controller IntelAhci && \
VBoxManage storageattach rayen-os-test --storagectl SATA --port 0 --device 0 --type dvddrive --medium output/rayen-os-*.iso"

docker:
	@docker build -t rayen-os-builder .
	@docker run --privileged -v $(PWD):/build rayen-os-builder

distclean: clean
	@sudo rm -rf config/ config.bak/ cache/ 2>/dev/null || true
	@echo "Distclean done."
