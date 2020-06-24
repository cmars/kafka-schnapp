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

import os
import shutil
import re
import socket
from subprocess import check_call

from pathlib import Path
from base64 import b64encode

from charmhelpers.core import hookenv, host
from charmhelpers.core.templating import render

from charms.reactive.relations import RelationBase

from charms.layer import snap

KAFKA_PORT = 9093
KAFKA_SNAP = 'kafka'
KAFKA_SERVICE = 'snap.{}.kafka.service'.format(KAFKA_SNAP)
KAFKA_SNAP_DATA = '/var/snap/{}/common'.format(KAFKA_SNAP)


def caKeystore():
    return os.path.join(
        KAFKA_SNAP_DATA,
        "kafka.server.truststore.jks"
    )


def caPath():
    return '/usr/local/share/ca-certificates/{}.crt'.format(
        hookenv.service_name()
    )


def crtPath(cert_type):
    return os.path.join(
        KAFKA_SNAP_DATA,
        "{}.crt".format(cert_type)
    )


def keyPath(cert_type):
    return os.path.join(
        KAFKA_SNAP_DATA,
        "{}.key".format(cert_type)
    )


def keystore(cert_type):
    return os.path.join(
        KAFKA_SNAP_DATA,
        "kafka.{}.jks".format(cert_type)
    )


def keystoreSecret():
    return os.path.join(
        KAFKA_SNAP_DATA,
        'keystore.secret'
    )


class Kafka(object):
    def open_ports(self):
        '''
        Attempts to open the Kafka port.
        '''
        hookenv.open_port(KAFKA_PORT)

    def close_ports(self):
        '''
        Attempts to close the Kafka port.
        '''
        hookenv.close_port(KAFKA_PORT)

    def install(self, zk_units=[], log_dir='logs'):
        '''
        Generates client-ssl.properties and server.properties with the current
        system state.
        '''
        zks = []
        for unit in zk_units or self.get_zks():
            ip = resolve_private_address(unit['host'])
            zks.append('%s:%s' % (ip, unit['port']))
        zks.sort()
        zk_connect = ','.join(zks)

        config = hookenv.config()

        broker_id = None
        storageids = hookenv.storage_list('logs')
        if storageids:
            mount = hookenv.storage_get('location', storageids[0])

            if mount:
                broker_path = os.path.join(log_dir, '.broker_id')

                if os.path.isfile(broker_path):
                    with open(broker_path, 'r') as f:
                        try:
                            broker_id = int(f.read().strip())
                        except ValueError:
                            hookenv.log('{}'.format(
                                'invalid broker id format'))
                            hookenv.status_set(
                                'blocked',
                                'unable to validate broker id format')
                            raise

        if broker_id is None:
            hookenv.status_set(
                'blocked',
                'unable to get broker id')
            return

        context = {
            'broker_id': broker_id,
            'port': KAFKA_PORT,
            'zookeeper_connection_string': zk_connect,
            'log_dirs': log_dir,
            'keystore_password': keystore_password(),
            'ca_keystore': caKeystore(),
            'server_keystore': keystore('server'),
            'client_keystore': keystore('client'),
            'bind_addr': hookenv.unit_private_ip(),
            'auto_create_topics': config['auto_create_topics'],
            'default_partitions': config['default_partitions'],
            'default_replication_factor': config['default_replication_factor'],
            'inter_broker_protocol_version':
                config.get('inter_broker_protocol_version'),
            'log_message_format_version':
                config.get('log_message_format_version'),
        }

        render(
            source='client-ssl.properties',
            target=os.path.join(KAFKA_SNAP_DATA, 'client-ssl.properties'),
            owner='root',
            perms=0o400,
            context=context
        )

        render(
            source='server.properties',
            target=os.path.join(KAFKA_SNAP_DATA, 'server.properties'),
            owner='root',
            perms=0o644,
            context=context
        )

        render(
            source='broker.env',
            target=os.path.join(KAFKA_SNAP_DATA, 'broker.env'),
            owner='root',
            perms=0o644,
            context={
                'kafka_heap_opts': config.get('kafka_heap_opts', ''),
            }
        )

        render(
            source='override.conf',
            target='/etc/systemd/system/snap.kafka.kafka.service.d/override.conf',
            owner='root',
            perms=0o644,
            context={},
        )
        check_call(['systemctl', 'daemon-reload'], universal_newlines=True)

        log4j_file = os.path.join(KAFKA_SNAP_DATA, 'log4j.properties')
        if config.get('log4j_properties'):
            with open(log4j_file, 'w') as f:
                print(config['log4j_properties'], file=f)
        elif os.path.exists(log4j_file):
            os.unlink(log4j_file)

        if log_dir:
            os.makedirs(log_dir, mode=0o700, exist_ok=True)
            shutil.chown(log_dir, user='root')

        self.restart()

    def restart(self):
        '''
        Restarts the Kafka service.
        '''
        host.service_restart(KAFKA_SERVICE)

    def start(self):
        '''
        Starts the Kafka service.
        '''
        host.service_reload(KAFKA_SERVICE)

    def stop(self):
        '''
        Stops the Kafka service.

        '''
        host.service_stop(KAFKA_SERVICE)

    def is_running(self):
        '''
        Restarts the Kafka service.
        '''
        return host.service_running(KAFKA_SERVICE)

    def get_zks(self):
        '''
        Will attempt to read zookeeper nodes from the zookeeper.joined state.

        If the flag has never been set, an empty list will be returned.
        '''
        zk = RelationBase.from_flag('zookeeper.joined')
        if zk:
            return zk.zookeepers()
        else:
            return []

    def version(self):
        '''
        Will attempt to get the version from the version fieldof the
        Kafka snap file.

        If there is a reader exception or a parser exception, unknown
        will be returned
        '''
        return snap.get_installed_version(KAFKA_SNAP) or 'unknown'


def keystore_password():
    path = keystoreSecret()
    if not os.path.isfile(path):
        with os.fdopen(
                os.open(path, os.O_WRONLY | os.O_CREAT, 0o440),
                'wb') as f:
            token = b64encode(os.urandom(32))
            f.write(token)
            password = token.decode('ascii')
    else:
        password = Path(path).read_text().rstrip()
    return password


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
            raise ValueError(
                'Unable to resolve private-address: {}'.format(addr)
            )
        return contained.groups(0).replace('-', '.')
