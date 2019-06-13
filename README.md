# kafka-schnapp

It's a snap. It's a charm. It's a schnapp.

This project compiles Kafka 2.2.1 from source into a snap and embeds that into
a charm that then operates it. Because the snap is installed locally, there is
no concern over auto-upgrades in snaps.

# Building

    make sysdeps
    make all

Will build the Kafka snap, and then the charm in `charm/builds/kafka`.

# Operating

This charm does not require any configuration. It relates to zookeeper and
scales horizontally by adding units. It supports Juju storage.

The snap uses strict confinement with the removable-media plug to support
storage.

    juju deploy ./charm/builds/kafka
    juju deploy zookeeper
    juju relate kafka zookeeper

The charm also supports storage:

    juju add-storage kafka/0 logs=1G

# Notes

The Kafka charm requires at least 4GB of memory.

# Details

Much of the charm implementation is borrowed from the Apache Bigtop kafka
charm, but it's been heavily simplified and pared down. Jinja templating is
used instead of Puppet, and a few helper functions that were imported from
libraries are inlined.

---
