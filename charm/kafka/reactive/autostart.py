from charms.layer.kafka import Kafka

from charmhelpers.core import hookenv

from charms.reactive import when, set_flag, set_state, clear_flag, remove_state


@when('kafka.available', 'zookeeper.ready')
def autostart_service():
    '''
    Attempt to restart the service if it is not running.
    '''
    kafka = Kafka()
    zks = kafka.get_zks()

    if kafka.is_running():
        hookenv.status_set('active', 'ready ({} zk unit(s))'.format(len(zks)))
        return

    for i in range(3):
        hookenv.status_set(
            'maintenance',
            'attempting to restart kafka, '
            'attempt: {}'.format(i+1)
        )
        kafka.restart()
        if kafka.is_running():
            hookenv.status_set(
                'active',
                'ready ({} zk unit(s))'.format(len(zks))
            )
            return

    hookenv.status_set('blocked', 'failed to start kafka; check syslog')
