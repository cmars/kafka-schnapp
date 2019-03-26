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

from charms.reactive import (when, when_not, hook,
                             remove_state, set_state)
from charms.reactive.helpers import data_changed


@when('snap.installed.kafka')
@when_not('kafka.zk.disabled')
def disable_bootstrap_zk():
    check_call([
        'systemctl', 'disable',
        'snap.{}.zookeeper.service'.format(KAFKA_SNAP)
    ])
    set_state('kafka.zk.disabled')


@when('kafka.available')
@when_not('zookeeper.joined')
def waiting_for_zookeeper():
    hookenv.status_set('blocked', 'waiting for relation to zookeeper')


@when('kafka.available', 'zookeeper.joined')
@when_not('kafka.started', 'zookeeper.ready')
def waiting_for_zookeeper_ready(zk):
    hookenv.status_set('waiting', 'waiting for zookeeper to become ready')


@hook('upgrade-charm')
def upgrade_charm():
    remove_state('kafka.started')
    remove_state('zookeeper.nrpe_helper.installed')


@hook('config-changed')
def config_changed():
    remove_state('kafka.zk.disabled')


@when_not(
    'kafka.ca.keystore.saved',
    'kafka.server.keystore.saved'
)
@when('kafka.available')
def waiting_for_certificates():
    hookenv.status_set('waiting', 'waiting for easyrsa relation')


@when(
    'snap.installed.kafka',
    'zookeeper.ready',
    'kafka.ca.keystore.saved',
    'kafka.server.keystore.saved'
)
@when_not('kafka.started')
def configure_kafka(zk):
    hookenv.status_set('maintenance', 'setting up kafka')
    log_dir = unitdata.kv().get('kafka.storage.log_dir')
    data_changed('kafka.storage.log_dir', log_dir)
    kafka = Kafka()
    zks = zk.zookeepers()
    kafka.install(zk_units=zks, log_dir=log_dir)
    kafka.open_ports()
    set_state('kafka.started')
    hookenv.status_set('active', 'ready')
    # set app version string for juju status output
    kafka_version = kafka.version()
    hookenv.application_version_set(kafka_version)


@when('kafka.started', 'zookeeper.ready')
def configure_kafka_zookeepers(zk):
    """Configure ready zookeepers and restart kafka if needed.
    As zks come and go, server.properties will be updated. When that file
    changes, restart Kafka and set appropriate status messages.
    """
    zks = zk.zookeepers()
    log_dir = unitdata.kv().get('kafka.storage.log_dir')
    if not(any((
            data_changed('zookeepers', zks),
            data_changed('kafka.storage.log_dir', log_dir)))):
        return

    hookenv.log('Checking Zookeeper configuration')
    hookenv.status_set('maintenance', 'updating zookeeper instances')
    kafka = Kafka()
    kafka.install(zk_units=zks, log_dir=log_dir)
    hookenv.status_set('active', 'ready')


@when('kafka.started')
@when_not('zookeeper.ready')
def stop_kafka_waiting_for_zookeeper_ready():
    hookenv.status_set('maintenance', 'zookeeper not ready, stopping kafka')
    kafka = Kafka()
    kafka.close_ports()
    kafka.stop()
    remove_state('kafka.started')
    hookenv.status_set('waiting', 'waiting for zookeeper to become ready')


@when('client.joined', 'zookeeper.ready')
def serve_client(client, zookeeper):
    client.send_port(KAFKA_PORT)
    client.send_zookeepers(zookeeper.zookeepers())

    hookenv.log('Sent Kafka configuration to client')
