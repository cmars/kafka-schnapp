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

import ipaddress
import os
import netifaces
import re
import shutil
import socket
from subprocess import check_output

from charmhelpers.core import hookenv, host
from charmhelpers.core.templating import render


KAFKA_PORT=9092
KAFKA_SNAP='kafka'
KAFKA_SERVICE='snap.{}.kafka.service'.format(KAFKA_SNAP)
KAFKA_SNAP_DATA='/var/snap/{}/current'.format(KAFKA_SNAP)


class Kafka(object):

    def open_ports(self):
        hookenv.open_port(KAFKA_PORT)

    def close_ports(self):
        hookenv.close_port(KAFKA_PORT)

    def configure_kafka(self, zk_units, network_interface=None, log_dir=None):
        # Get ip:port data from our connected zookeepers
        zks = []
        for unit in zk_units:
            ip = resolve_private_address(unit['host'])
            zks.append("%s:%s" % (ip, unit['port']))
        zks.sort()
        zk_connect = ",".join(zks)
        service, unit_num = os.environ['JUJU_UNIT_NAME'].split('/', 1)

        context = {
            'broker_id': unit_num,
            'port': KAFKA_PORT,
            'zookeeper_connection_string': zk_connect,
            'log_dirs': log_dir,
        }
        if network_interface:
            ip = get_ip_for_interface(network_interface)
            context['bind_addr'] = ip
        else:
            context['bind_addr'] = hookenv.unit_private_ip()

        render(source="server.properties",
                target=os.path.join(KAFKA_SNAP_DATA, 'server.properties'),
                owner="root",
                perms=0o644,
                context=context)

        if log_dir:
            os.makedirs(log_dir, mode=0o700, exist_ok=True)
            shutil.chown(log_dir, user='root')

        self.restart()

    def restart(self):
        self.stop()
        self.start()

    def start(self):
        host.service_start(KAFKA_SERVICE)

    def stop(self):
        host.service_stop(KAFKA_SERVICE)


def resolve_private_address(addr):
    IP_pat = re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
    contains_IP_pat = re.compile(r'\d{1,3}[-.]\d{1,3}[-.]\d{1,3}[-.]\d{1,3}')
    if IP_pat.match(addr):
        return addr  # already IP
    try:
        ip = socket.gethostbyname(addr)
        return ip
    except socket.error as e:
        hookenv.log('Unable to resolve private IP: %s (will attempt to guess)' % addr, hookenv.ERROR)
        hookenv.log('%s' % e, hookenv.ERROR)
        contained = contains_IP_pat.search(addr)
        if not contained:
            raise ValueError('Unable to resolve or guess IP from private-address: %s' % addr)
        return contained.groups(0).replace('-', '.')


    def get_ip_for_interface(self, network_interface):
        """
        Helper to return the ip address of this machine on a specific
        interface.

        @param str network_interface: either the name of the
        interface, or a CIDR range, in which we expect the interface's
        ip to fall. Also accepts 0.0.0.0 (and variants, like 0/0) as a
        special case, which will simply return what you passed in.

        """
        if network_interface.startswith('0') or network_interface == '::':
            # Allow users to reset the charm to listening on any
            # interface.  Allow operators to specify this however they
            # wish (0.0.0.0, ::, 0/0, etc.).
            return network_interface

        # Is this a CIDR range, or an interface name?
        is_cidr = len(network_interface.split(".")) == 4 or len(
            network_interface.split(":")) == 8

        if is_cidr:
            interfaces = netifaces.interfaces()
            for interface in interfaces:
                try:
                    ip = netifaces.ifaddresses(interface)[2][0]['addr']
                except KeyError:
                    continue

                if ipaddress.ip_address(ip) in ipaddress.ip_network(
                        network_interface):
                    return ip

            raise Exception(
                u"This machine has no interfaces in CIDR range {}".format(
                    network_interface))
        else:
            try:
                ip = netifaces.ifaddresses(network_interface)[2][0]['addr']
            except ValueError:
                raise BigtopError(
                    u"This machine does not have an interface '{}'".format(
                        network_interface))
            return ip
