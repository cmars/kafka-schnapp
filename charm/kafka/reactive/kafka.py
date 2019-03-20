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

import glob
import os
import yaml
import socket
import tempfile
import shutil

from subprocess import check_call, CalledProcessError
from pathlib import Path
from OpenSSL import crypto

from charmhelpers.core import hookenv, unitdata
from charms.layer.kafka import Kafka, KAFKA_PORT, KAFKA_SNAP, KAFKA_SNAP_DATA
from charms.layer import tls_client
from charms.reactive import set_state, remove_state, when, when_not, hook, when_file_changed
from charms.reactive.helpers import data_changed
from charmhelpers.core.hookenv import log

@when_not('kafka.available')
def install():
    install_snap()

@hook('upgrade-charm')
def upgrade():
    install_snap(upgrade=True)

@hook('config-changed')
def config_changed():
    install_snap(upgrade=True)

@hook('stop')
def uninstall():
    try:
        check_call(['snap', 'remove', 'kafka'])
    except CalledProcessError as e:
        hookenv.log("failed to remove snap: {}".format(e))

def install_snap(upgrade=False):
    # Need to install the core snap explicit. If not, there's
    # no slots for removable-media on a bionic install.
    # Not sure if that's a snapd bug or intended behavior.
    check_call(['snap', 'install', 'core'])

    cfg = hookenv.config()
    # Kafka's snap presedence is:
    # 1. Included in snap
    # 2. Included with resource of charm of 'kafka'
    # 3. Snap store with release channel specified in config
    snap_file = get_snap_file_from_charm() or hookenv.resource_get('kafka')
    if snap_file:
        hookenv.log('Detected Kafka snap, installing/refreshing {}'.format(snap_file))
        check_call(['snap', 'install', '--dangerous', snap_file])
    if not snap_file:
        hookenv.log('No Kafka snap detected in charm, installing from snapstore with channel {}'.format(cfg['kafka-release-channel']))
        
        if upgrade:
            check_call(['snap', 'refresh', '--{}'.format(cfg['kafka-release-channel']), KAFKA_SNAP])
        else:
            check_call(['snap', 'install', '--{}'.format(cfg['kafka-release-channel']), KAFKA_SNAP])

    # Disable the zookeeper daemon included in the snap, only run kafka
    check_call(['systemctl', 'disable', 'snap.{}.zookeeper.service'.format(KAFKA_SNAP)])
    set_state('kafka.available')


def get_snap_file_from_charm():
    snap_files = sorted(glob.glob(os.path.join(hookenv.charm_dir(), "{}*.snap".format(KAFKA_SNAP))))[::-1]
    if not snap_files:
        return None
    return snap_files[0]


@when('kafka.available')
@when_not('zookeeper.joined')
def waiting_for_zookeeper():
    hookenv.status_set('blocked', 'waiting for relation to zookeeper')


@when('kafka.available', 'zookeeper.joined')
@when_not('kafka.started', 'zookeeper.ready')
def waiting_for_zookeeper_ready(zk):
    hookenv.status_set('waiting', 'waiting for zookeeper to become ready')


@when_not(
    'kafka.ca.keystore.saved',
    'kafka.server.keystore.saved'
)
@when('kafka.available')
def waiting_for_certificates():
    hookenv.status_set('waiting', 'waiting for easyrsa relation')


@when(
    'kafka.available',
    'zookeeper.ready',
    'kafka.ca.keystore.saved',
    'kafka.server.keystore.saved'
)
@when_not('kafka.started')
def configure_kafka(zk):
    if len(zk.zookeepers()) < 1:
        hookenv.status_set('blocked', 'waiting for >= 1 zookeeper units')
        return

    hookenv.status_set('maintenance', 'setting up kafka')
    log_dir = unitdata.kv().get('kafka.storage.log_dir')
    data_changed('kafka.storage.log_dir', log_dir)
    kafka = Kafka()
    zks = zk.zookeepers()
    kafka.configure_kafka(zks, log_dir=log_dir)
    kafka.open_ports()
    set_state('kafka.started')
    hookenv.status_set('active', 'ready')
    # set app version string for juju status output
    kafka_version = get_package_version(KAFKA_SNAP) or 'unknown'
    hookenv.application_version_set(kafka_version)


def get_package_version(snap_name):
    with open('/snap/{}/current/meta/snap.yaml'.format(snap_name), 'r') as f:
        meta = yaml.load(f)
        return meta.get('version')
    return None


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

    if len(zks) < 1:
        hookenv.status_set('blocked', 'waiting for >= 1 zookeeper units')
        return

    hookenv.log('Checking Zookeeper configuration')
    hookenv.status_set('maintenance', 'updating zookeeper instances')
    kafka = Kafka()
    kafka.configure_kafka(zks, log_dir=log_dir)
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


@hook('logs-storage-attached')
def storage_attach():
    storageids = hookenv.storage_list('logs')
    if not storageids:
        hookenv.status_set('blocked', 'cannot locate attached storage')
        return
    storageid = storageids[0]

    mount = hookenv.storage_get('location', storageid)
    if not mount:
        hookenv.status_set('blocked', 'cannot locate attached storage mount')
        return

    log_dir = os.path.join(mount, "logs")
    unitdata.kv().set('kafka.storage.log_dir', log_dir)
    hookenv.log('Kafka logs storage attached at {}'.format(log_dir))
    # Stop Kafka; removing the kafka.started state will trigger
    # a reconfigure if/when it's ready
    kafka = Kafka()
    kafka.close_ports()
    kafka.stop()
    remove_state('kafka.started')
    hookenv.status_set('waiting', 'reconfiguring to use attached storage')
    set_state('kafka.storage.logs.attached')


@hook('logs-storage-detaching')
def storage_detaching():
    unitdata.kv().unset('kafka.storage.log_dir')
    kafka = Kafka()
    kafka.close_ports()
    kafka.stop()
    remove_state('kafka.started')
    hookenv.status_set('waiting', 'reconfiguring to use temporary storage')
    remove_state('kafka.storage.logs.attached')


@when('certificates.available')
def send_data():
    # Send the data that is required to create a server certificate for
    # this server.

    # Use the private ip of this unit as the Common Name for the certificate.
    common_name = hookenv.unit_private_ip()

    # Create SANs that the tls layer will add to the server cert.
    sans = [
        common_name,
        socket.gethostname(),
    ]

    # Request a server cert with this information.
    tls_client.request_server_cert(
        common_name,
        sans,
        crt_path=os.path.join(
            KAFKA_SNAP_DATA,
            "server.crt"
        ),
        key_path=os.path.join(
            KAFKA_SNAP_DATA,
            "server.key"
        )
    )
    tls_client.request_client_cert(
        'system:snap-kafka',
        crt_path=os.path.join(
            KAFKA_SNAP_DATA,
            'client.crt',
        ),
        key_path=os.path.join(
            KAFKA_SNAP_DATA,
            'client.key'
        )
    )


@when_file_changed(os.path.join(KAFKA_SNAP_DATA, "kafka.server.jks"))
@when_file_changed(os.path.join(KAFKA_SNAP_DATA, "kafka.client.jks"))
def restart_when_keystore_changed():
    Kafka().restart()


@when('tls_client.certs.changed')
def import_srv_crt_to_keystore():
    for cert_type in ('server', 'client'):
        keystore_path = os.path.join(
            KAFKA_SNAP_DATA,
            "kafka.{}.jks".format(cert_type)
        )
        keystore_password = _keystore_password()
        crt_path = os.path.join(
            KAFKA_SNAP_DATA,
            "{}.crt".format(cert_type)
        )
        key_path = os.path.join(
            KAFKA_SNAP_DATA,
            "{}.key".format(cert_type)
        )
        if os.path.isfile(crt_path) and os.path.isfile(key_path):
            cert = open(crt_path, 'rt').read()
            loaded_cert = crypto.load_certificate(
                crypto.FILETYPE_PEM,
                cert
            )
            key = open(key_path, 'rt').read()
            loaded_key = crypto.load_privatekey(
                crypto.FILETYPE_PEM,
                key
            )

            cert_changed = data_changed(
                'kafka_{}_certificate'.format(cert_type),
                cert
            )
            log('server certificate changed {changed}'.format(changed=cert_changed))
            if cert_changed:
                log('server certificate changed')
                pkcs12 = crypto.PKCS12Type()
                pkcs12.set_certificate(loaded_cert)
                pkcs12.set_privatekey(loaded_key)
                pkcs12_data = pkcs12.export(keystore_password)
                fd, path = tempfile.mkstemp()
                log('opening tmp file {}'.format(path))
                try:
                    with os.fdopen(fd, 'wb') as tmp:
                        # write cert and private key to the pkcs12 file
                        tmp.write(pkcs12_data)
                        log('Writing pkcs12 temporary file {0}'.format(
                            path
                        ))
                        tmp.close()
                        log('importing pkcs12')
                        # import the pkcs12 into the keystore
                        check_call(
                            '/snap/kafka/current/usr/lib/jvm/default-java/bin/keytool -v -importkeystore -srckeystore {path} -srcstorepass {password} -srcstoretype PKCS12 -destkeystore {keystore} -deststoretype JKS -deststorepass {password} --noprompt'.format(
                                path=path,
                                password=keystore_password,
                                keystore=keystore_path
                            ),
                            shell=True
                        )
                        os.chmod(keystore_path, 0o440)
                        remove_state('tls_client.certs.changed')
                        set_state('kafka.{}.keystore.saved'.format(cert_type))
                finally:
                    os.remove(path)
        else:
            log('server certificate of key file missing'.format(
                cert=os.path.isfile(crt_path),
                key=os.path.isfile(key_path)
            ))


@when('tls_client.ca_installed')
@when_not('kafka.ca.keystore.saved')
def import_ca_crt_to_keystore():
    service_name = hookenv.service_name()
    ca_path = '/usr/local/share/ca-certificates/{0}.crt'.format(service_name)

    if os.path.isfile(ca_path):
        with open(ca_path, 'rt') as f:
            ca_cert = f.read()
            changed = data_changed('ca_certificate', ca_cert)
        if changed:
            ca_keystore = os.path.join(
                KAFKA_SNAP_DATA,
                "kafka.server.truststore.jks"
            )
            password = _keystore_password()
            check_call(
                '/snap/kafka/current/usr/lib/jvm/default-java/bin/keytool -import -trustcacerts -keystore {keystore} -storepass  {keystorepass} -file {path} -noprompt'.format(
                    path=ca_path,
                    keystore=ca_keystore,
                    keystorepass=password
                ),
                shell=True
            )
            os.chmod(ca_keystore, 0o440)
            remove_state('tls_client.ca_installed')
            set_state('kafka.ca.keystore.saved')

@when('kafka.started')
def health_check():
    # Health check will attempt to restart Kafka service, if the service is not running
    kafka = Kafka()
    if kafka.is_running():
        hookenv.status_set('active', 'ready')
        return

    for i in range(3):
        hookenv.status_set('maintenance', 'attempting to restart kafka, attempt: {}'.format(i+1))
        kafka.restart()
        if kafka.is_running():
            hookenv.status_set('active', 'ready')
            return

    hookenv.status_set('blocked', 'failed to start kafka; check syslog')

def _keystore_password():
    path = os.path.join(
        KAFKA_SNAP_DATA,
        "keystore.secret"
    )
    if not os.path.isfile(path):
        _ensure_directory(path)
        check_call(
            ['head -c 32 /dev/urandom | base64 > {}'.format(path)],
            shell=True
        )
        os.chmod(path, 0o440)
    password = Path(path).read_text()
    return password.rstrip()


def _ensure_directory(path):
    '''Ensure the parent directory exists creating directories if necessary.'''
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    os.chmod(directory, 0o770)
