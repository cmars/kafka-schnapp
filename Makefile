
KAFKA_VERSION := $(shell awk '/version:/ {print $$2}' snap/snapcraft.yaml | head -1 | sed "s/'//g")

.PHONY: all
all: snap lint charm

.PHONY: lint
lint:
	flake8 --ignore=E121,E123,E126,E226,E24,E704,E265 charm/kafka

.PHONY: schnapp
schnapp: snap fat-charm

.PHONY: snap
snap: kafka_$(KAFKA_VERSION)_amd64.snap

kafka_$(KAFKA_VERSION)_amd64.snap:
	SNAPCRAFT_BUILD_ENVIRONMENT_MEMORY=6G snapcraft

.PHONY: fat-charm
fat-charm: kafka_$(KAFKA_VERSION)_amd64.snap
	cp $< charm/kafka/
	$(MAKE) -C charm/kafka

.PHONY: charm
charm: charm/builds/kafka

charm/builds/kafka:
	$(MAKE) -C charm/kafka

.PHONY: clean
clean: clean-charm clean-snap

.PHONY: clean-charm
clean-charm:
	$(RM) -r charm/builds charm/deps
	$(RM) charm/kafka/*.snap

.PHONY: clean-snap
clean-snap:
	snapcraft clean
	rm -f kafka_$(KAFKA_VERSION)_amd64.snap

sysdeps: /snap/bin/charm /snap/bin/snapcraft
/snap/bin/charm:
	sudo snap install charm --classic
/snap/bin/snapcraft:
	sudo snap install snapcraft --classic
