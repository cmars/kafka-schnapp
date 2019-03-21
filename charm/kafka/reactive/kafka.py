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

from subprocess import check_call

from charms.layer.kafka import Kafka, KAFKA_PORT, KAFKA_SNAP

from charmhelpers.core import hookenv, unitdata

from charms.reactive import (set_state, remove_state, when, when_not,
                             hook, clear_flag, is_flag_set, set_flag,
                             when_any)
from charms.reactive.helpers import data_changed

from charmhelpers.core.hookenv import log

from charms.layer import snap

@when('snap.installed.kafka')
@when_not('kafka.zk.disabled')
def disable_bootstrap_zk():
    check_call([
        'systemctl', 'disable',
        'snap.{}.zookeeper.service'.format(KAFKA_SNAP)
    ])
    set_state('kafka.zk.disabled')


@hook('upgrade-charm')
def upgrade_charm():
    remove_state('kafka.zk.disabled')


@hook('config-changed')
def config_changed():
    remove_state('kafka.available')
    remove_state('kafka.configured')
    set_flag('kafka.force-reconfigure')


@when('snap.installed.kafka')
@when_not('kafka.configured')
def configure():
    kafka = Kafka()
    zks = kafka.get_zks()
    log_dir = unitdata.kv().get('kafka.storage.log_dir')
    changed = any((
        data_changed('kafka.zk_units', zks),
        data_changed('kafka.log_dir', log_dir)
    ))

    if changed or is_flag_set('kafka.force-reconfigure'):
        kafka.install(zk_units=zks, log_dir=log_dir)
        kafka.open_ports()

    clear_flag('kafka.force-reconfigure')
    set_state('kafka.available')
    set_state('kafka.configured')

    hookenv.application_version_set(kafka.version())


@when('snap.installed.kafka')
@when_not(
    'kafka.ca.keystore.saved',
    'kafka.server.keystore.saved'
)
def waiting_for_certificates():
    hookenv.status_set('waiting', 'waiting for easyrsa relation')


@when('snap.installed.kafka')
@when_not('zookeeper.ready')
def waiting_for_zookeeper():
    hookenv.status_set('waiting', 'waiting for zookeeper relation')


@when(
    'snap.installed.kafka',
    'zookeeper.ready',
    'kafka.ca.keystore.saved',
    'kafka.server.keystore.saved'
)
@when_not('kafka.available')
def configure_kafka(zk):
    hookenv.status_set('maintenance', 'setting up kafka')

    log_dir = unitdata.kv().get('kafka.storage.log_dir')
    data_changed('kafka.storage.log_dir', log_dir)

    remove_state('kafka.configured')
    set_flag('kafka.force-reconfigure')


@when('kafka.configured')
@when_any('zookeeper.started')
def configure_kafka_zookeepers(zk):
    """
    Configure ready zookeepers and restart kafka if needed.

    As zks come and go, server.properties will be updated. When that file
    changes, restart Kafka and set appropriate status messages.
    """
    zks = zk.zookeepers()

    if not data_changed('kafka.zk_units', zks):
        return

    log('zookeeper(s) joined, forcing reconfiguration')
    remove_state('kafka.configured')
    set_flag('kafka.force-reconfigure')


@when('client.joined', 'zookeeper.ready')
def serve_client(client, zookeeper):
    client.send_port(KAFKA_PORT)
    client.send_zookeepers(zookeeper.zookeepers())

    hookenv.log('Sent Kafka configuration to client')
