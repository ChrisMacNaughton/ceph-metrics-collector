#!/usr/bin/python

import setup

setup.pre_install()
from charmhelpers.core.hookenv import Hooks, UnregisteredHookError, log, relation_get, related_units
import sys
import subprocess

hooks = Hooks()


@hooks.hook('config-changed')
def config_changed():
    restart()


@hooks.hook('start')
def start():
    try:
        subprocess.check_call(['service', 'decode_ceph', 'start'])
    except subprocess.CalledProcessError as err:
        # todo: log levels should be an enum
        log('Service decode_ceph start failed with return code: {}'.format(err.returncode),
            level='INFO')


@hooks.hook('stop')
def stop():
    # Find all started listener processes
    try:
        subprocess.check_call(['service', 'decode_ceph', 'stop'])
    except subprocess.CalledProcessError as err:
        log('Service decode_ceph start failed with return code: {}'.format(err.returncode),
            level='INFO')


def restart():
    try:
        subprocess.check_call(['service', 'decode_ceph', 'restart'])
    except subprocess.CalledProcessError as err:
        log('Service decode_ceph start failed with return code: {}'.format(err.returncode),
            level='INFO')


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
