# kafka-schnapp

It's a snap. It's a charm. It's a schnapp.

This project compiles Kafka from source into a snap and embeds that into
a charm that then operates it. Because the snap is installed locally, there is
no concern over auto-upgrades in snaps.

# Building

    make sysdeps
    make all

Will build the Kafka snap, and then the charm in `charm/builds/kafka`.

# Quick start

    cd charm
    juju deploy ./bundle.yaml

# Notes

The Kafka charm requires at least 4GB of memory.

# Details

Much of the charm implementation is borrowed from the Apache Bigtop kafka
charm, but it's been heavily simplified and pared down. Jinja templating is
used instead of Puppet, and a few helper functions that were imported from
libraries are inlined.

---
