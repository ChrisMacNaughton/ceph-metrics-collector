#!/usr/bin/python
import requests

import setup

setup.pre_install()
from charmhelpers.core.hookenv import (
    Hooks,
    UnregisteredHookError,
    log,
    relation_get, config,
    related_units,
    status_set,
    is_leader,
    relations_of_type,
)
from charmhelpers.core.host import service_restart, service_stop, service_start
import os
import sys
import subprocess
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


# TODO: Unit test this
# Takes 2 dictionaries and combines their key/values with a unique set of outputs list
def combine_dicts(a, b):
    outputs = []
    if 'outputs' not in a:
        outputs = b['outputs']
        del b['outputs']
    elif 'outputs' not in b:
        outputs = a['outputs']
        del a['outputs']
    else:
        outputs = list(set(a['outputs'] + b['outputs']))
    c = dict(a, **b)
    c['outputs'] = outputs
    return c


def write_config(service_dict):
    try:
        with open(config_file, 'w+') as config:
            config.write(
                # {'elasticsearch': '127.0.0.7', 'outputs': ['elasticsearch', 'stdout'] }
                dump(data=service_dict, Dumper=Dumper))
    except IOError as err:
        log("IOError with {}:{}".format(config_file, err.message))


# Expects a list of output types: ['stdout', 'elasticsearch', 'etc']
# and also a dict of params for that service: {'elasticsearch': '127.0.0.1'}
def update_service_config(service_dict):
    # assert isinstance(option_list, list)
    assert isinstance(service_dict, dict)

    # Write it out if the file doesn't exist
    if not os.path.exists(config_file):
        log('creating new service config file: ' + str(service_dict))
        write_config(service_dict)
    try:
        with open(config_file, 'r+') as config:
            try:
                data = load(config, Loader=Loader)
                new_service_dict = combine_dicts(data, service_dict)
                log('Writing combined service dict: ' + str(new_service_dict))
                write_config(new_service_dict)
            except SyntaxError as err:
                # Yaml config file is screwed up.  Write out a fresh one.  We could lose options here by accident
                # Todo: this should really utilize a tmp file + mv to ensure atomic file operation in case of crashes
                log('Invalid syntax found in /etc/decode.conf.  Overwriting with new file. ' + err.message)
                log('Overwriting service dict: ' + str(service_dict))
                write_config(service_dict)
    except IOError as err:
        log("IOError with /etc/default/decode_ceph.yaml " + err.message)


@hooks.hook('config-changed')
def config_changed():
    if config('influx_host') != '':
        host = config('influx_host')
        port = config('influx_port')
        user = config('influx_user')
        password = config('influx_password')
        setup_influx(host, port, user, password)
        restart()


@hooks.hook('start')
def start():
    try:
        service_start('decode_ceph')
    except subprocess.CalledProcessError as err:
        log('Service restart failed with err: ' + err.message)
    try:
        service_start('ceph_monitor')
    except subprocess.CalledProcessError as err:
        log('Service restart failed with err: ' + err.message)


@hooks.hook('stop')
def stop():
    try:
        service_stop('decode_ceph')
    except subprocess.CalledProcessError as err:
        log('Service restart failed with err: ' + err.message)
    try:
        service_stop('ceph_monitor')
    except subprocess.CalledProcessError as err:
        log('Service restart failed with err: ' + err.message)


def restart():
    try:
        service_restart('decode_ceph')
    except subprocess.CalledProcessError as err:
        log('Service restart failed with err: ' + err.message)
    try:
        service_restart('ceph_monitor')
    except subprocess.CalledProcessError as err:
        log('Service restart failed with err: ' + err.message)


@hooks.hook('collector-relation-changed')
def collector_relation_changed():
    host = relation_get('hostname')
    port = relation_get('port')

    # Check the list length so pop doesn't fail
    if host is None or port is None:
        log('host or port is none')
        return
    else:
        relation_data = relations_of_type('ceph')
        if not relation_data:
            return
        try:
            hostname = subprocess.check_output(['hostname', '-f']).replace('.', '_').rstrip('\n')
            relation = relation_data[0]["__unit__"]
            unit_tag = "unit-{0}".format(relation.replace('/', '-'))
            log("unit_tag: " + str(unit_tag))
            root_key = "{unit_tag}.{hostname}.ceph".format(unit_tag=unit_tag,
                                                           hostname=hostname)

            carbon = {
                'host': host,
                'port': port,
                'root_key': root_key
            }

            update_service_config(service_dict={'outputs': ['carbon'], 'carbon': carbon})
            restart()
        except subprocess.CalledProcessError as err:
            log('Service restart failed with err: ' + err.message)


@hooks.hook('carbon-relation-changed')
def carbon_relation_changed():
    carbon_server = related_units()
    update_service_config(service_dict={'outputs': ['carbon'], 'carbon': carbon_server})
    restart()


@hooks.hook('db-api-relation-changed')
def db_api_relation_changed():
    host = relation_get('hostname')
    port = relation_get('port')
    user = relation_get('user')
    password = relation_get('password')
    if host is None or port is None or user is None or password is None:
        log("Do not have the configuration for InfluxDB")
        return

    setup_influx(host, port, user, password)
    restart()


def setup_influx(host, port, user, password):
    influx = {
        'host': host,
        'port': port,
        'user': user,
        'password': password
    }
    if is_leader():
        query = 'create database "ceph"'
        url = 'http://{}:{}/query?q={}'.format(influx['host'], influx['port'], query)
        log("Setting up ceph database using {}".format(url))
        requests.get(url)
        query = 'CREATE RETENTION POLICY "one_week" ON "ceph" DURATION 7d REPLICATION 1 DEFAULT'
        log("Setting up ceph database retention policy using {}".format(url))
        url = 'http://{}:{}/query?q={}'.format(influx['host'], influx['port'], query)
        requests.get(url)
    update_service_config(service_dict={'outputs': ['influx'], 'influx': influx})

if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
        status_set('active', '')
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
