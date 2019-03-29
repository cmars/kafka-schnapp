#!/bin/bash

set -eu

if [ ! -f $SNAP_COMMON/server.properties ]; then
	echo "configuration file $SNAP_COMMON/server.properties does not exist."
	exit 1
fi

export PATH=$SNAP/usr/lib/jvm/default-java/bin:$PATH
export LOG_DIR=$SNAP_COMMON/log

$SNAP/opt/kafka/bin/kafka-server-start.sh $SNAP_COMMON/server.properties
