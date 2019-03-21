# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import ipaddress
import os
import re
import shutil
import socket

from pathlib import Path

from charmhelpers.core import hookenv, host
from charmhelpers.core.templating import render


KAFKA_PORT=9093
KAFKA_SNAP='kafka'
KAFKA_SERVICE='snap.{}.kafka.service'.format(KAFKA_SNAP)
KAFKA_SNAP_DATA='/var/snap/{}/common'.format(KAFKA_SNAP)

class Kafka(object):
    def open_ports(self):
        hookenv.open_port(KAFKA_PORT)

    def close_ports(self):
        hookenv.close_port(KAFKA_PORT)

    def configure_kafka(self, zk_units, log_dir=None):
        # Get ip:port data from our connected zookeepers
        zks = []
        for unit in zk_units:
            ip = resolve_private_address(unit['host'])
            zks.append("%s:%s" % (ip, unit['port']))
        zks.sort()
        zk_connect = ",".join(zks)

        context = {
            'broker_id': os.environ['JUJU_UNIT_NAME'].split('/', 1)[1],
            'port': KAFKA_PORT,
            'zookeeper_connection_string': zk_connect,
            'log_dirs': log_dir,
            'keystore_password': _read_keystore_password(),
            'ca_keystore': os.path.join(
                KAFKA_SNAP_DATA,
                "kafka.server.truststore.jks"
            ),
            'server_keystore': os.path.join(
                KAFKA_SNAP_DATA,
                "kafka.server.jks"
            ),
            'client_keystore': os.path.join(
                KAFKA_SNAP_DATA,
                "kafka.client.jks"
            ),
            'bind_addr': hookenv.unit_private_ip()
        }

        render(
            source="client-ssl.properties",
            target=os.path.join(KAFKA_SNAP_DATA, 'client-ssl.properties'),
            owner="root",
            perms=0o400,
            context=context
        )

        render(
            source="server.properties",
            target=os.path.join(KAFKA_SNAP_DATA, 'server.properties'),
            owner="root",
            perms=0o644,
            context=context
        )

        if log_dir:
            os.makedirs(log_dir, mode=0o700, exist_ok=True)
            shutil.chown(log_dir, user='root')

        self.restart()

    def restart(self):
        self.stop()
        self.start()

    def start(self):
        host.service_start(KAFKA_SERVICE)

    def stop(self):
        host.service_stop(KAFKA_SERVICE)
    
    def is_running(self):
        return host.service_running(KAFKA_SERVICE)

def resolve_private_address(addr):
    IP_pat = re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
    contains_IP_pat = re.compile(r'\d{1,3}[-.]\d{1,3}[-.]\d{1,3}[-.]\d{1,3}')
    if IP_pat.match(addr):
        return addr  # already IP
    try:
        ip = socket.gethostbyname(addr)
        return ip
    except socket.error as e:
        hookenv.log(
            'Unable to resolve private IP: %s (will attempt to guess)' %
            addr,
            hookenv.ERROR
        )
        hookenv.log('%s' % e, hookenv.ERROR)
        contained = contains_IP_pat.search(addr)
        if not contained:
            raise ValueError('Unable to resolve or guess IP from private-address: %s' % addr)
        return contained.groups(0).replace('-', '.')

def _read_keystore_password():
    path = os.path.join(
        KAFKA_SNAP_DATA,
        "keystore.secret"
    )
    password = Path(path).read_text()
    return password.rstrip()
