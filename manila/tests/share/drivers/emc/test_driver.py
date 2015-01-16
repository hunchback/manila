# Copyright (c) 2014 EMC Corporation.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
from stevedore import extension

from manila.openstack.common import log as logging
from manila.share import configuration as conf
from manila.share.drivers.emc import driver as emcdriver
from manila.share.drivers.emc.plugins import base
from manila import test

LOG = logging.getLogger(__name__)


class FakeConnection(base.StorageConnection):
    def __init__(self, logger):
        self.logger = logger

    @property
    def driver_handles_share_servers(self):
        return True

    def create_share(self, emc_share_driver, context, share, share_server):
        """Is called to create share."""
        pass

    def create_snapshot(self, emc_share_driver, context,
                        snapshot, share_server):
        """Is called to create snapshot."""
        pass

    def delete_share(self, emc_share_driver, context, share, share_server):
        """Is called to remove share."""
        pass

    def delete_snapshot(self, emc_share_driver, context,
                        snapshot, share_server):
        """Is called to remove snapshot."""
        pass

    def ensure_share(self, emc_share_driver, context, share, share_server):
        """Invoked to sure that share is exported."""
        pass

    def allow_access(self, emc_share_driver, context, share,
                     access, share_server):
        """Allow access to the share."""
        pass

    def deny_access(self, emc_share_driver, context, share,
                    access, share_server):
        """Deny access to the share."""
        pass

    def raise_connect_error(self, emc_share_driver):
        """Check for setup error."""
        pass

    def connect(self, emc_share_driver, context):
        """Any initialization the share driver does while starting."""
        raise NotImplementedError()

    def update_share_stats(self, stats_dict):
        """Add key/values to stats_dict."""
        pass

    def get_network_allocations_number(self):
        """Returns number of network allocations for creating VIFs."""
        return 0

    def setup_server(self, network_info, metadata=None):
        """Set up and configures share server with given network parameters."""
        pass

    def teardown_server(self, server_details, security_services=None):
        """Teardown share server."""
        pass

FAKE_BACKEND = 'fake_backend'


class FakeEMCExtensionManager():
    def __init__(self):
        self.extensions = []
        self.extensions.append(
            extension.Extension(name=FAKE_BACKEND,
                                plugin=FakeConnection,
                                entry_point=None,
                                obj=None))


class EMCShareFrameworkTestCase(test.TestCase):

    @mock.patch('stevedore.extension.ExtensionManager',
                mock.Mock(return_value=FakeEMCExtensionManager()))
    def setUp(self):
        super(EMCShareFrameworkTestCase, self).setUp()
        self.configuration = conf.Configuration(None)
        self.configuration.append_config_values = mock.Mock(return_value=0)
        self.configuration.share_backend_name = FAKE_BACKEND
        self.stubs.Set(self.configuration, 'safe_get', self._fake_safe_get)
        self.driver = emcdriver.EMCShareDriver(
            configuration=self.configuration)

    def test_driver_setup(self):
        FakeConnection.connect = mock.Mock()
        self.driver.do_setup(None)
        self.assertIsInstance(self.driver.plugin, FakeConnection,
                              "Not an instance of FakeConnection")
        FakeConnection.connect.assert_called_with(self.driver, None)

    def test_update_share_stats(self):
        data = {}
        self.driver.plugin = mock.Mock()
        self.driver._update_share_stats()
        data["share_backend_name"] = FAKE_BACKEND
        data["driver_handles_share_servers"] = True
        data["vendor_name"] = 'EMC'
        data["driver_version"] = '1.0'
        data["storage_protocol"] = 'NFS_CIFS'
        data['total_capacity_gb'] = 'infinite'
        data['free_capacity_gb'] = 'infinite'
        data['reserved_percentage'] = 0
        data['QoS_support'] = False
        self.assertEqual(data, self.driver._stats)

    def _fake_safe_get(self, value):
        if value in ['emc_share_backend', 'share_backend_name']:
            return FAKE_BACKEND
        elif value == 'driver_handles_share_servers':
            return True
        return None
