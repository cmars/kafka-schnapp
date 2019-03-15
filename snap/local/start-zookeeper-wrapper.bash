#!/bin/bash

set -eu

if [ ! -f $SNAP_COMMON/zookeeper.properties ]; then
	cp $SNAP/opt/kafka/config/zookeeper.properties $SNAP_COMMON/zookeeper.properties
fi

export PATH=$SNAP/usr/lib/jvm/default-java/bin:$PATH
export LOG_DIR=$SNAP_COMMON/log

$SNAP/opt/kafka/bin/zookeeper-server-start.sh $SNAP_COMMON/zookeeper.properties
