#!/bin/bash

set -eu

if [ ! -f $SNAP_COMMON/server.properties ]; then
	cp $SNAP/opt/kafka/config/server.properties $SNAP_COMMON/server.properties
fi

export PATH=$SNAP/usr/lib/jvm/default-java/bin:$PATH
export LOG_DIR=$SNAP_COMMON/log

# JMX is only available on localhost:9999
export JMX_PORT=${JMX_PORT:-9999}
export KAFKA_JMX_OPTS="-Djava.rmi.server.hostname=localhost \
-Djava.net.preferIPv4Stack=true \
-Dcom.sun.management.jmxremote -Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false"

$SNAP/opt/kafka/bin/kafka-server-start.sh $SNAP_COMMON/server.properties
