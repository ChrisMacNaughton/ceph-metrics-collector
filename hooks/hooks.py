#!/usr/bin/python
import setup

setup.pre_install()
import os
import subprocess
from charmhelpers.core.hookenv import Hooks, UnregisteredHookError, log, relation_get, related_units
import sys
import signal
import time

hooks = Hooks()


@hooks.hook('config-changed')
def config_changed():
    pass


@hooks.hook('start')
def start():
    working_dir = os.getcwd()
    log('working dir: ' + str(working_dir))
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

        os.kill(pid_id, signal.SIGTERM)
        time.sleep(5)
        # It should exit quickly but if it doesn't
        os.kill(pid_id, signal.SIGKILL)


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
