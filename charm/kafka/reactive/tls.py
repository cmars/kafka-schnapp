import os
import socket
import tempfile

from OpenSSL import crypto
from subprocess import check_call

from charms.layer import tls_client
from charms.layer.kafka import keystore_password, KAFKA_SNAP_DATA

from charmhelpers.core import hookenv

from charms.reactive import (when, when_file_changed, remove_state,
                             when_not, set_state, set_flag)
from charms.reactive.helpers import data_changed

from charmhelpers.core.hookenv import log


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
    extra_names = hookenv.config().get('subject_alt_names', '')
    sans.extend([n.strip() for n in extra_names.split(',') if n])

    # Request a server cert with this information.
    tls_client.request_server_cert(
        common_name,
        sans,
        crt_path=os.path.join(
            KAFKA_SNAP_DATA,
            'server.crt'
        ),
        key_path=os.path.join(
            KAFKA_SNAP_DATA,
            'server.key'
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


@when_file_changed(os.path.join(KAFKA_SNAP_DATA, 'kafka.server.jks'))
@when_file_changed(os.path.join(KAFKA_SNAP_DATA, 'kafka.client.jks'))
def restart_when_keystore_changed():
    remove_state('kafka.configured')
    set_flag('kafka.force-reconfigure')


@when('tls_client.certs.changed')
def import_srv_crt_to_keystore():
    for cert_type in ('server', 'client'):
        password = keystore_password()
        crt_path = os.path.join(
            KAFKA_SNAP_DATA,
            "{}.crt".format(cert_type)
        )
        key_path = os.path.join(
            KAFKA_SNAP_DATA,
            "{}.key".format(cert_type)
        )

        if os.path.isfile(crt_path) and os.path.isfile(key_path):
            with open(crt_path, 'rt') as f:
                cert = f.read()
                loaded_cert = crypto.load_certificate(
                    crypto.FILETYPE_PEM,
                    cert
                )
                if not data_changed(
                    'kafka_{}_certificate'.format(cert_type),
                    cert
                ):
                    log('server certificate of key file missing')
                    return

            with open(key_path, 'rt') as f:
                loaded_key = crypto.load_privatekey(
                    crypto.FILETYPE_PEM,
                    f.read()
                )

            with tempfile.NamedTemporaryFile() as tmp:
                log('server certificate changed')

                keystore_path = os.path.join(
                    KAFKA_SNAP_DATA,
                    "kafka.{}.jks".format(cert_type)
                )

                pkcs12 = crypto.PKCS12Type()
                pkcs12.set_certificate(loaded_cert)
                pkcs12.set_privatekey(loaded_key)
                pkcs12_data = pkcs12.export(password)
                log('opening tmp file {}'.format(tmp.name))

                # write cert and private key to the pkcs12 file
                tmp.write(pkcs12_data)
                tmp.flush()

                log('importing pkcs12')
                # import the pkcs12 into the keystore
                check_call([
                    'keytool',
                    '-v', '-importkeystore',
                    '-srckeystore', str(tmp.name),
                    '-srcstorepass', password,
                    '-srcstoretype', 'PKCS12',
                    '-destkeystore', keystore_path,
                    '-deststoretype', 'JKS',
                    '-deststorepass', password,
                    '--noprompt'
                ])
                os.chmod(keystore_path, 0o440)

                remove_state('tls_client.certs.changed')
                set_state('kafka.{}.keystore.saved'.format(cert_type))


@when('tls_client.ca_installed')
@when_not('kafka.ca.keystore.saved')
def import_ca_crt_to_keystore():
    ca_path = '/usr/local/share/ca-certificates/{}.crt'.format(
        hookenv.service_name()
    )

    if os.path.isfile(ca_path):
        with open(ca_path, 'rt') as f:
            changed = data_changed('ca_certificate', f.read())

        if changed:
            ca_keystore = os.path.join(
                KAFKA_SNAP_DATA,
                "kafka.server.truststore.jks"
            )
            check_call([
                'keytool',
                '-import', '-trustcacerts', '-noprompt',
                '-keystore', ca_keystore,
                '-storepass', keystore_password(),
                '-file', ca_path
            ])
            os.chmod(ca_keystore, 0o440)

            remove_state('tls_client.ca_installed')
            set_state('kafka.ca.keystore.saved')
