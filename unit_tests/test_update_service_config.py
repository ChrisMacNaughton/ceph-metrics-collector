__author__ = 'chris'

import sys
import mock
import unittest
from pkg_resources import resource_filename
from yaml import load

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

# allow importing actions from the hooks directory
sys.path.append(resource_filename(__name__, '../hooks'))
from hooks import update_service_config


# Note this must run as root or it will fail to write the config file
class TestHooks(unittest.TestCase):
    @mock.patch('charmhelpers.core.hookenv.log')
    def test_service_config(self, log):
        update_service_config(['elasticsearch'], {'elasticsearch': '127.0.0.1'})
        with open('/etc/default/decode_ceph.yaml', 'r') as conf_file:
            yaml_conf = load(conf_file, Loader=Loader)
            assert isinstance(yaml_conf['outputs'], list)
            assert isinstance(yaml_conf['elasticsearch'], basestring)
            print yaml_conf
            assert yaml_conf['outputs'] == ['elasticsearch']


if __name__ == '__main__':
    unittest.main()
