#!/bin/bash

set -eu

if [ ! -f $SNAP_DATA/zookeeper.properties ]; then
	cp $SNAP/opt/kafka/config/zookeeper.properties $SNAP_DATA/zookeeper.properties
fi

export LOG_DIR=$SNAP_DATA/log

$SNAP/opt/kafka/bin/zookeeper-server-start.sh $SNAP_DATA/zookeeper.properties
