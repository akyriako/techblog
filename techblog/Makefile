REGISTRY   := quay.io
NAMESPACE  ?= akyriako
IMAGE      := techblog
TAG        ?= latest

IMAGE_REF := $(REGISTRY)/$(NAMESPACE)/$(IMAGE):$(TAG)

.PHONY: login build push release

login:
	docker login $(REGISTRY)

build:
	docker build -t $(IMAGE_REF) .

push:
	docker push $(IMAGE_REF)

release: build push
	@echo "Published $(IMAGE_REF)"