from charmhelpers.core import hookenv

from charms.reactive import hook, set_flag

from charms.layer import snap


@hook('stop')
def uninstall():
    try:
        snap.remove('kafka')
    except Exception as e:
        # log errors but do not fail stop hook
        hookenv.log('failed to remove snap: {}'.format(e), hookenv.ERROR)
    finally:
        set_flag('kafka.departed')
