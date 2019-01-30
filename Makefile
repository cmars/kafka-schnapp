
KAFKA_VERSION := $(shell awk '/version:/ {print $$2}' snap/snapcraft.yaml | head -1 | sed "s/'//g")

.PHONY: all
all: snap charm

.PHONY: snap
snap: kafka_$(KAFKA_VERSION)_amd64.snap

kafka_$(KAFKA_VERSION)_amd64.snap:
	snapcraft cleanbuild

.PHONY: charm
charm: charm/builds/kafka

charm/builds/kafka: kafka_$(KAFKA_VERSION)_amd64.snap
	cp $< charm/kafka
	$(MAKE) -C charm/kafka

.PHONY: clean
clean: clean-charm clean-snap

.PHONY: clean-charm
clean-charm:
	$(RM) -r charm/builds charm/deps

.PHONY: clean-snap
clean-snap:
	snapcraft clean

