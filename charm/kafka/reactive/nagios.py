import os
import shutil

from charmhelpers.core import hookenv

from charms.reactive import when, when_not, set_state

from charms.layer.kafka import KAFKA_SNAP


@when('local-monitors.available')
def local_monitors_available(nagios):
    setup_nagios(nagios)


@when('nrpe-external-master.available')
def nrpe_external_master_available(nagios):
    setup_nagios(nagios)


def setup_nagios(nagios):
    config = hookenv.config()
    unit_name = hookenv.local_unit()
    checks = [{
        'name': 'underreplicated_partitions_count',
        'object_name': 'kafka.server:type=ReplicaManager,\
name=UnderReplicatedPartitions',
        'description': 'Number of under replicated partitions',
        'crit': 'val != 0',
    }, {
        'name': 'active_controller_count',
        'object_name': 'kafka.controller:type=KafkaController,\
name=ActiveControllerCount',
        'description': 'Number of active controllers in cluster',
        'crit': 'val != 1'
    }, {
        'name': 'offline_partitions_count',
        'object_name': 'kafka.controller:type=KafkaController,\
name=OfflinePartitionsCount',
        'description': 'Number of offline partitions in cluster',
        'crit': 'val != 0'
    }, {
        'name': 'leader_election_rate',
        'object_name': 'kafka.controller:type=ControllerStats,\
name=LeaderElectionRateAndTimeMs',
        'attribute': 'OneMinuteRate',
        'description': 'Leader election rate and latency in milliseconds',
        'warn': 'val >= {}'.format(config['nagios_leader_election_rate_warn']),
        'crit': 'val >= {}'.format(config['nagios_leader_election_rate_crit'])
    }, {
        'name': 'producer_time',
        'object_name': 'kafka.network:type=RequestMetrics,\
name=TotalTimeMs,request=Produce',
        'attribute': '99thPercentile',
        'description': 'The top 99th percentile total time \
in milliseconds to produce a message',
        'warn': 'val >= {}'.format(config['nagios_producer_time_warn']),
        'crit': 'val >= {}'.format(config['nagios_producer_time_crit'])
    }, {
        'name': 'consumer_fetch_time',
        'object_name': 'kafka.network:type=RequestMetrics,\
name=TotalTimeMs,request=FetchConsumer',
        'attribute': '99thPercentile',
        'description': 'The top 99th percentile total time\
in milliseconds for a consumer to fetch data',
        'warn': 'val >= {}'.format(config['nagios_consumer_fetch_time_warn']),
        'crit': 'val >= {}'.format(config['nagios_consumer_fetch_time_crit'])
    }, {
        'name': 'avg_network_processor_idle',
        'object_name': 'kafka.network:name=NetworkProcessorAvgIdlePercent,\
type=SocketServer',
        'description': 'Average idle percentage of the network processor',
        'warn': 'val <= {}'.format(
            config['nagios_avg_network_processor_idle_warn']
        ),
        'crit': 'val <= {}'.format(
            config['nagios_avg_network_processor_idle_crit']
        )
    }]

    check_cmd = [
        'python3', '/usr/local/lib/nagios/plugins/check_kafka_jmx.py'
    ]

    for check in checks:
        cmd = check_cmd + [
            '--run-path',
            '/snap/{}/current/opt/kafka/bin/kafka-run-class.sh'.format(
                KAFKA_SNAP
            ),
            '--object-name', check['object_name']
        ]
        if 'warn' in check:
            cmd += ['-w', "'{}'".format(check['warn'])]
        if 'crit' in check:
            cmd += ['-c', "'{}'".format(check['crit'])]
        if 'attribute' in check:
            cmd += ['-a', "'{}'".format(check['attribute'])]

        nagios.add_check(
            cmd,
            name=check['name'],
            description=check['description'],
            context=config['nagios_context'],
            servicegroups=(
                config.get('nagios_servicegroups') or config['nagios_context']
            ),
            unit=unit_name
        )
    nagios.updated()
    set_state('kafka.nrpe_helper.registered')


@when('kafka.nrpe_helper.registered')
@when_not('kafka.nrpe_helper.installed')
def install_nrpe_helper():
    dst_dir = '/usr/local/lib/nagios/plugins/'
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
    src = '{}/files/check_kafka_jmx.py'.format(hookenv.charm_dir())
    dst = '{}/check_kafka_jmx.py'.format(dst_dir)
    shutil.copy(src, dst)
    os.chmod(dst, 0o755)
    set_state('kafka.nrpe_helper.installed')
