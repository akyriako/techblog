
REGISTRY   := quay.io
NAMESPACE  ?= akyriako
IMAGE      := techblog
TAG        ?= latest

IMAGE_REF := $(REGISTRY)/$(NAMESPACE)/$(IMAGE):$(TAG)

TRIVY_CACHE_DIR ?= $(HOME)/.cache/trivy
SCAN_SEVERITY ?= HIGH,CRITICAL,UNKNOWN

.PHONY: login build scan scan-all check-root push release clean-trivy-cache

login:
	docker login $(REGISTRY)

build:
	docker build --pull -t $(IMAGE_REF) .

scan scan-all:
	@set -eu; \
	tmp=$$(mktemp -d); \
	trap 'rm -rf "$$tmp"' EXIT HUP INT TERM; \
	mkdir -p "$(TRIVY_CACHE_DIR)"; \
	echo "Fetching latest Trivy version..."; \
	curl -fsSL --retry 3 \
	  https://api.github.com/repos/aquasecurity/trivy/releases/latest \
	  -o "$$tmp/release.json"; \
	version=$$(grep -m1 '"tag_name"' "$$tmp/release.json" \
	  | cut -d '"' -f4); \
	test -n "$$version" || { \
	  echo "Failed to determine Trivy version"; \
	  exit 1; \
	}; \
	echo "Installing Trivy $$version into $$tmp"; \
	curl -fsSL --retry 3 \
	  https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
	  -o "$$tmp/install.sh"; \
	sh "$$tmp/install.sh" -b "$$tmp" "$$version"; \
	if [ "$@" = "scan-all" ]; then \
	  severity=UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL; \
	  exit_code=0; \
	else \
	  severity='$(SCAN_SEVERITY)'; \
	  exit_code=1; \
	fi; \
	echo "Scanning $(IMAGE_REF)..."; \
	"$$tmp/trivy" image \
	  --cache-dir "$(TRIVY_CACHE_DIR)" \
	  --scanners vuln \
	  --severity "$$severity" \
	  --exit-code "$$exit_code" \
	  "$(IMAGE_REF)"

check-root:
	@echo "Checking container runtime user..."
	@uid=$$(docker run --rm --entrypoint id $(IMAGE_REF) -u); \
	if [ "$$uid" = "0" ]; then \
	  echo "ERROR: Container runs as root"; \
	  exit 1; \
	fi; \
	echo "OK: Container runs as UID $$uid"

push:
	docker push $(IMAGE_REF)

release: build scan check-root push
	@echo "Published $(IMAGE_REF)"

clean-trivy-cache:
	@echo "Removing Trivy cache..."
	rm -rf "$(TRIVY_CACHE_DIR)"
