from charms.layer.kafka import Kafka

from charmhelpers.core import hookenv

from charms.reactive import when


@when('kafka.started', 'zookeeper.ready')
def autostart_service():
    '''
    Attempt to restart the service if it is not running.
    '''
    kafka = Kafka()

    if kafka.is_running():
        hookenv.status_set('active', 'ready')
        return

    for i in range(3):
        hookenv.status_set(
            'maintenance',
            'attempting to restart kafka, '
            'attempt: {}'.format(i+1)
        )
        kafka.restart()
        if kafka.is_running():
            hookenv.status_set('active', 'ready')
            return

    hookenv.status_set('blocked', 'failed to start kafka; check syslog')
