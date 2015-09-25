#!/usr/bin/python
from charmhelpers.core.hookenv import Hooks, UnregisteredHookError, log, relation_get, related_units
import sys
import setup

setup.pre_install()

hooks = Hooks()


@hooks.hook('config-changed')
def config_changed():
    pass


@hooks.hook('start')
def start():
    pass


@hooks.hook('stop')
def stop():
    pass


@hooks.hook('ceph-relation-changed')
def ceph_relation_changed():
    pass


@hooks.hook('elasticsearch-relation-changed')
def elasticsearch_relation_changed():
    cluster_name = relation_get('cluster-name')
    es_host_list = []
    for member in related_units():
        es_host_list.push(relation_get('private-address {}'.format(member)))


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
