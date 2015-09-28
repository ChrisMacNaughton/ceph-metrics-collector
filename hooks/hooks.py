#!/usr/bin/python
import setup

setup.pre_install()
from charmhelpers.core.hookenv import Hooks, UnregisteredHookError, log, relation_get, related_units
import json
import netifaces
import os
import sys
import signal
import subprocess
import time

hooks = Hooks()


@hooks.hook('config-changed')
def config_changed():
    pass


# Find the network interfaces to listen on based on the ceph.conf info
def find_interfaces():
    # 1. Is this machine running an OSD?
    # 2. What interface is it listening on?
    interfaces_to_listen_on = []
    interfaces = netifaces.interfaces()
    osd_dump = subprocess.check_output(['ceph', 'osd', 'dump', '--format', 'json'])
    try:
        osd_json = json.loads(osd_dump)
        for osd in osd_json['osds']:
            public_addr = osd['public_addr']
            log('OSD public addr: ' + str(public_addr))
            # Example ipv4 output: 10.0.3.213:6800/10784
            parts = public_addr.rstrip().split(':')
            if len(parts) != 2:
                log('Unable to decipher the ip address of the osd from: ' + public_addr)
                return -1
            addr = parts[0]
            log('OSD addr: ' + str(addr))
            # For each interface check to see if the IP addr matches an OSD ip addr.
            # If it does then we'll save it so that we can listen on that addr
            try:
                for i in interfaces:
                    interface_ip_info = netifaces.ifaddresses(i)[netifaces.AF_INET]
                    log('interface ip info: ' + str(interface_ip_info))
                    # If the OSD addr == the addr we own then add that to the listening list
                    if interface_ip_info[0]['addr'] is addr:
                        interfaces_to_listen_on.append(i)
            except KeyError:
                # I don't care about interfaces that don't have IP info on them
                pass
        return interfaces_to_listen_on
    except ValueError as err:
        log('Unable to decode json from ceph.  Error is: ' + err.message)


@hooks.hook('start')
def start():
    working_dir = os.getcwd()
    log('working dir: ' + str(working_dir))
    listen_interfaces = find_interfaces()
    log('Found listen interfaces: ' + str(listen_interfaces))
    proc = subprocess.Popen(["hooks/decode_ceph", "-i", "eth0"], shell=True, cwd=working_dir)
    # Write pid to /var/run/decode_ceph
    with open('/var/run/decode_ceph', 'w+') as pid_file:
        pid_file.write(str(proc.pid))


@hooks.hook('stop')
def stop():
    with open('/var/run/decode_ceph', 'r') as pid_file:
        pid = pid_file.readlines()
        # Give a chance to stop nicely
        pid_id = int(pid[0].strip())
        assert isinstance(pid_id, int)

        try:
            os.kill(pid_id, signal.SIGTERM)
            time.sleep(5)
            # It should exit quickly but if it doesn't
            os.kill(pid_id, signal.SIGKILL)
        except OSError as err:
            log('Unable to find decode_ceph process: ' + err.message)


def restart_collectors():
    pass


@hooks.hook('elasticsearch-relation-changed')
def elasticsearch_relation_changed():
    cluster_name = relation_get('cluster-name')
    es_host_list = []
    for member in related_units():
        es_host_list.append(relation_get('private-address {}'.format(member)))
    restart_collectors()


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
