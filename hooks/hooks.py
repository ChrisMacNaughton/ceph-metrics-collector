#!/usr/bin/python
import requests

import setup

setup.pre_install()
from charmhelpers.core.hookenv import Hooks, UnregisteredHookError, log, relation_get, related_units, charm_dir, \
    status_set, is_leader
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

config_file = '/etc/default/decode_ceph.yaml'


def juju_header():
    header = ("#-------------------------------------------------#\n"
              "# This file is Juju managed - do not edit by hand #\n"
              "#-------------------------------------------------#\n")
    return header


def write_config(outputs_list, service_dict):
    data = {}
    data.update(service_dict)
    data['outputs'] = outputs_list

    try:
        with open(config_file, 'w+') as config:
            config.write(
                # {'elasticsearch': '127.0.0.7', 'outputs': ['elasticsearch', 'stdout'] }
                dump(data=data, Dumper=Dumper))
    except IOError as err:
        log("IOError with {}:{}".format(config_file, err.message))


# Expects a list of output types: ['stdout', 'elasticsearch', 'etc']
# and also a dict of params for that service: {'elasticsearch': '127.0.0.1'}
def update_service_config(option_list, service_dict):
    assert isinstance(option_list, list)
    assert isinstance(service_dict, dict)

    # Write it out if the file doesn't exist
    if not os.path.exists(config_file):
        write_config(option_list, service_dict)
    try:
        with open(config_file, 'r+') as config:
            try:
                data = load(config, Loader=Loader)
                if 'outputs' in data:
                    output_list = data['outputs']
                    # Merge the lists
                    new_options = list(set(option_list + output_list))
                    write_config(new_options, service_dict)
                else:
                    # outputs is missing.  Overwrite it
                    write_config(option_list, service_dict)
            except SyntaxError as err:
                # Yaml config file is screwed up.  Write out a fresh one.  We could lose options here by accident
                # Todo: this should really utilize a tmp file + mv to ensure atomic file operation in case of crashes
                log('Invalid syntax found in /etc/decode.conf.  Overwriting with new file. ' + err.message)
                write_config(option_list, service_dict)
    except IOError as err:
        log("IOError with /etc/decode.conf. " + err.message)


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
    try:
        subprocess.check_call(['service', 'ceph_monitor', 'stop'])
    except subprocess.CalledProcessError as err:
        log('Service ceph_monitor start failed with return code: {}'.format(err.returncode),
            level='ERROR')


def restart():
    try:
        subprocess.check_call(['service', 'decode_ceph', 'restart'])
    except subprocess.CalledProcessError as err:
        log('Service decode_ceph start failed with return code: {}'.format(err.returncode),
            level='ERROR')
    try:
        subprocess.check_call(['service', 'ceph_monitor', 'restart'])
    except subprocess.CalledProcessError as err:
        log('Service ceph_monitor start failed with return code: {}'.format(err.returncode),
            level='ERROR')


# Creates an index in elasticsearch if it did not exist
def create_es_index(url):
    result = requests.get(url)
    if result.status_code != requests.codes.ok:
        # Doesn't exist.  Lets create it
        status_set('maintenance', 'Creating index on elasticsearch for {}'.format(url))
        index_create = requests.put(url)
        if index_create.status_code != requests.codes.ok:
            log('Unable to create index on Elasticsearch for {}'.format(url), level='error')
        status_set('maintenance', '')


# Open a file and set that mapping in elasticsearch
def set_es_mapping(url, file_name):
    status_set('maintenance', 'Loading mappings for {} into elasticsearch from {}'.format(url, file_name))
    with open('files/{}'.format(file_name), 'r') as payload:
        response = requests.post(url, data=payload)
        if response.status_code != requests.codes.ok:
            # Try the next server in the cluster
            log('Unable to set index mapping on Elasticsearch for {}'.format(url), level='error')
    status_set('maintenance', '')


# Add an index to Elasticsearch with an explicit mapping
def setup_kibana_index(elasticsearch_servers):
    log('elastic servers' + str(elasticsearch_servers))
    if is_leader():
        server = elasticsearch_servers[0]  # save a reference to the first server

        create_es_index("http://{}:9200/.kibana".format(server))

        set_es_mapping("http://{}:9200/.kibana/_mapping/config".format(server), "kibana_config_mapping.json")
        set_es_mapping("http://{}:9200/.kibana/_mapping/dashboard".format(server), "kibana_dashboard_mapping.json")
        set_es_mapping("http://{}:9200/.kibana/_mapping/index".format(server), "kibana_index_mapping.json")
        set_es_mapping("http://{}:9200/.kibana/_mapping/search".format(server), "kibana_search_mapping.json")

        # Now load the config data
        set_es_mapping("http://{}:9200/.kibana/index-pattern/ceph".format(server), "ceph_index.json")
        set_es_mapping("http://{}:9200/.kibana/index-pattern/logstash-*".format(server), "logstash_index.json")
        # TODO: Still need to set the default index.  How do we do that?

    status_set('maintenance', '')


# Add an index to Elasticsearch with an explicit mapping
def setup_ceph_index(elasticsearch_servers):
    log('elastic servers' + str(elasticsearch_servers))
    if is_leader():
        # Prevent everyone from trying the same thing
        # Check if the index exists first
        server = elasticsearch_servers[0]  # save a reference to the first server
        create_es_index("http://{}:9200/ceph".format(server))
        set_es_mapping("http://{}:9200/ceph/_mapping/operations".format(server), "elasticsearch_mapping.json")
    status_set('maintenance', '')


@hooks.hook('elasticsearch-relation-changed')
def elasticsearch_relation_changed():
    es_host_list = []
    for member in related_units():
        es_host_list.append(relation_get('private-address', member))
    # Check the list length so pop doesn't fail
    if len(es_host_list) > 0:
        add_elasticsearch_to_logstash(es_host_list)
        setup_ceph_index(es_host_list)
        setup_kibana_index(es_host_list)
        server = es_host_list[0]
        update_service_config(option_list=['elasticsearch'], service_dict={'elasticsearch': server + ":9200"})
        try:
            service_restart('logstash')
            service_restart('decode_ceph')
            service_restart('ceph_monitor')
        except subprocess.CalledProcessError as err:
            log('Service restart failed with err: ' + err.message)
    else:
        log('Unable to find elasticsearch related units')


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
    carbon_server = related_units()
    update_service_config(option_list=['carbon'], service_dict={'carbon': carbon_server})
    try:
        service_restart('decode_ceph')
    except subprocess.CalledProcessError as err:
        log('Service restart failed with err: ' + err.message)


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
        status_set('active', '')
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
