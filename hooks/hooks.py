#!/usr/bin/python
import glob

import setup

setup.pre_install()
from charmhelpers.core.hookenv import Hooks, UnregisteredHookError, log, relation_get, related_units
import netifaces
import os
import sys
import signal
import subprocess
import time

hooks = Hooks()


@hooks.hook('config-changed')
def config_changed():
    restart()


@hooks.hook('start')
def start():
    working_dir = os.getcwd()
    interfaces = netifaces.interfaces()

    '''
    if listen_interfaces is None:
        status_set('maintenance', 'Failed to find interfaces. Waiting on Ceph to start')
        return

    status_set('maintenance', 'Starting Ceph listener')
    '''
    for interface in interfaces:
        if interface == 'lo':
            # Skip loopback
            continue
        try:
            process = subprocess.Popen("hooks/decode_ceph -i {} 2>&1 > decode_ceph.out".format(interface),
                                       shell=True, cwd=working_dir, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            # Write pid to /var/run/decode_ceph
            try:
                with open('/var/run/decode_ceph' + interface, 'w+') as pid_file:
                    pid_file.write(str(process.pid))
            except IOError as err:
                log('Unable to write pid file for ceph interface: {}.  Error: {}'.format(
                    interface, err.message))
        except subprocess.CalledProcessError:
            # todo: log levels should be an enum
            log('Unable to find pid file for listener on interface {}'.format(interface),
                level='INFO')


@hooks.hook('stop')
def stop():
    # Find all started listener processes
    results = glob.glob('/var/run/decode_ceph*')
    for path in results:
        try:
            with open(path, 'r') as pid_file:
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
                    log('Unable to kill decode_ceph process: ' + err.message)
        except IOError as err:
            log('Unable to open pid file for ceph listener: {}.  Error: {}'.format(
                path, err.message))


def restart():
    stop()
    start()


@hooks.hook('elasticsearch-relation-changed')
def elasticsearch_relation_changed():
    cluster_name = relation_get('cluster-name')
    es_host_list = []
    for member in related_units():
        es_host_list.append(relation_get('private-address {}'.format(member)))


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
