#!/usr/bin/python

import setup

setup.pre_install()
from charmhelpers.core.hookenv import Hooks, UnregisteredHookError, log, relation_get, related_units, charm_dir
from charmhelpers.core.host import service_restart
import netifaces
import os
import sys
import subprocess
import time
from Cheetah.Template import Template
hooks = Hooks()

def jujuHeader():
    header = ("#-------------------------------------------------#\n"
              "# This file is Juju managed - do not edit by hand #\n"
              "#-------------------------------------------------#\n")
    return header

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
        es_host_list.append(relation_get('private-address', member))
        # es_host_list.append(relation_get('host'))
    add_elasticsearch_to_logstash(es_host_list)
    service_restart('logstash')

def add_elasticsearch_to_logstash(elasticsearch_servers):
    if elasticsearch_servers != []:
        tmplData = {}
        tmplData["elasticsearch_hosts"] = '["' + '","'.join(map(str, elasticsearch_servers)) + '"]'
        templateFile = os.path.join(charm_dir(), "templates", "es.conf.tmpl")
        t = Template(file=templateFile, searchList=tmplData)
        with open("/etc/logstash/conf.d/elasticsearch.conf", "w") as f:
            os.chmod("/etc/logstash/conf.d/elasticsearch.conf", 0644)
            f.write(jujuHeader())
            f.write(str(t))
    else:
        log("No elasticsearch servers found?")

if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
