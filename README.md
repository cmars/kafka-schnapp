# kafka-schnapp

It's a snap. It's a charm. It's a schnapp.

This project compiles Kafka 2.1.0 from source into a snap and embeds that into
a charm that then operates it. Because the snap is installed locally, there is
no concern over auto-upgrades in snaps.

Much of the charm implementation is borrowed from the Apache Bigtop kafka
charm, but it's been heavily simplified and pared down. Jinja templating is
used instead of puppet, and a few helper functions that were imported from
libraries are inlined.

This charm does not require any configuration. It relates to zookeeper and
scales horizontally by adding units. It supports Juju storage.

The snap uses strict confinement with the removable-media plug to support
storage.

Have fun.

---
