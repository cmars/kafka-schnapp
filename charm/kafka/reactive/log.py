import os

from charmhelpers.core import hookenv, unitdata

from charms.reactive import remove_state, hook, set_flag

from charmhelpers.core.hookenv import log


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
    remove_state('kafka.configured')
    set_flag('kafka.force-reconfigure')


@hook('logs-storage-detaching')
def storage_detaching():
    unitdata.kv().unset('kafka.storage.log_dir')

    log('log storage detatched, reconfiguring to use temporary storage')

    remove_state('kafka.configured')
    set_flag('kafka.force-reconfigure')

    remove_state('kafka.started')
    remove_state('kafka.storage.logs.attached')
