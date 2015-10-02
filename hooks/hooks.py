#!/usr/bin/python
import requests

import setup

setup.pre_install()
from charmhelpers.core.hookenv import Hooks, UnregisteredHookError, log, relation_get, related_units, charm_dir, \
    status_set
from charmhelpers.core.host import service_restart
import os
import sys
import subprocess
from Cheetah.Template import Template
from yaml import load, dump

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

hooks = Hooks()


def juju_header():
    header = ("#-------------------------------------------------#\n"
              "# This file is Juju managed - do not edit by hand #\n"
              "#-------------------------------------------------#\n")
    return header


def update_service_config(option_list):
    assert isinstance(option_list, list)
    try:
        with open('/etc/decode.conf', 'r+') as config:
            try:
                data = load(config, Loader=Loader)
                if 'outputs' in data:
                    output_list = data['outputs']
                    new_options = list(set(output_list) - set(option_list))
                    config.write(
                        dump(data={"outputs": new_options}, Dumper=Dumper))
                else:
                    # outputs is missing.  Overwrite it
                    config.write(
                        dump(data={"outputs": option_list}, Dumper=Dumper))

            except SyntaxError as err:
                # Yaml config file is screwed up.  Write out a fresh one.  We could lose options here by accident
                # Todo: this should really utilize a tmp file + mv to ensure atomic file operation in case of crashes
                log('Invalid syntax found in /etc/decode.conf.  Overwriting with new file. ' + err.message)
                config.write(
                    dump(data={"outputs": option_list}, Dumper=Dumper))
    except IOError as err:
        log("Unable to locate /etc/decode.conf. " + err.message)


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
            level='ERROR')


@hooks.hook('stop')
def stop():
    # Find all started listener processes
    try:
        subprocess.check_call(['service', 'decode_ceph', 'stop'])
    except subprocess.CalledProcessError as err:
        log('Service decode_ceph start failed with return code: {}'.format(err.returncode),
            level='ERROR')


def restart():
    try:
        subprocess.check_call(['service', 'decode_ceph', 'restart'])
    except subprocess.CalledProcessError as err:
        log('Service decode_ceph start failed with return code: {}'.format(err.returncode),
            level='ERROR')


# Add an index to Elasticsearch with an explicit mapping
def setup_ceph_index(elasticsearch_servers):
    log('elastic servers' + str(elasticsearch_servers))
    for server in elasticsearch_servers:
        # Check if the index exists first
        result = requests.get("http://{}:9200/ceph".format(server))
        if result.status_code != requests.codes.ok:
            # Doesn't exist.  Lets create it
            status_set('maintenance', 'Creating ceph index on elasticsearch')
            index_create = requests.put("http://{}:9200/ceph".format(server))
            if index_create.status_code != requests.codes.ok:
                # Try the next server in the cluster
                continue
            status_set('maintenance', '')

        status_set('maintenance', 'Loading mapping for ceph index into elasticsearch')
        with open('files/elasticsearch_mapping.json', 'r') as payload:
            response = requests.post("http://{}:9200/ceph/_mapping/operations".format(elasticsearch_servers[0]),
                                     data=payload)
            if response.status_code != requests.codes.ok:
                # Try the next server in the cluster
                continue
        break
    status_set('maintenance', '')


@hooks.hook('elasticsearch-relation-changed')
def elasticsearch_relation_changed():
    es_host_list = []
    for member in related_units():
        es_host_list.append(relation_get('private-address', member))
    add_elasticsearch_to_logstash(es_host_list)
    setup_ceph_index(es_host_list)
    update_service_config(['elasticsearch'])
    try:
        service_restart('logstash')
        service_restart('decode_ceph')
    except subprocess.CalledProcessError as err:
        log('Service restart failed with err: ' + err.message)


def add_elasticsearch_to_logstash(elasticsearch_servers):
    if elasticsearch_servers:
        tmpl_data = {"elasticsearch_hosts": '["' + '","'.join(map(str, elasticsearch_servers)) + '"]'}
        template_file = os.path.join(charm_dir(), "templates", "es.conf.tmpl")
        t = Template(file=template_file, searchList=tmpl_data)
        with open("/etc/logstash/conf.d/elasticsearch.conf", "w") as f:
            os.chmod("/etc/logstash/conf.d/elasticsearch.conf", 0644)
            f.write(juju_header())
            f.write(str(t))
    else:
        log("No elasticsearch servers found?")


@hooks.hook('carbon-relation-changed')
def carbon_relation_changed():
    pass


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
