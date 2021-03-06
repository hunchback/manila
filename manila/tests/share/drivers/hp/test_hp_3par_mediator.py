# Copyright 2015 Hewlett Packard Development Company, L.P.
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

import sys

import ddt
import mock
if 'hp3parclient' not in sys.modules:
    sys.modules['hp3parclient'] = mock.Mock()

from manila import exception
from manila.share.drivers.hp import hp_3par_mediator as hp3parmediator
from manila import test
from manila.tests.share.drivers.hp import test_hp_3par_constants as constants

from oslo_utils import units


@ddt.ddt
class HP3ParMediatorTestCase(test.TestCase):

    def setUp(self):
        super(HP3ParMediatorTestCase, self).setUp()

        # This is the fake client to use.
        self.mock_client = mock.Mock()

        # Take over the hp3parclient module and stub the constructor.
        hp3parclient = sys.modules['hp3parclient']

        # Need a fake constructor to return the fake client.
        # This is also be used for constructor error tests.
        self.mock_object(hp3parclient.file_client, 'HP3ParFilePersonaClient')
        self.mock_client_constructor = (
            hp3parclient.file_client.HP3ParFilePersonaClient
        )
        self.mock_client = self.mock_client_constructor()

        # Set the mediator to use in tests.
        self.mediator = hp3parmediator.HP3ParMediator(
            hp3par_username=constants.USERNAME,
            hp3par_password=constants.PASSWORD,
            hp3par_api_url=constants.API_URL,
            hp3par_debug=constants.EXPECTED_HP_DEBUG,
            hp3par_san_ip=constants.EXPECTED_IP_1234,
            hp3par_san_login=constants.SAN_LOGIN,
            hp3par_san_password=constants.SAN_PASSWORD,
            hp3par_san_ssh_port=constants.PORT,
            ssh_conn_timeout=constants.TIMEOUT)

    def test_mediator_setup_client_init_error(self):
        """Any client init exceptions should result in a ManilaException."""

        self.mock_client_constructor.side_effect = (
            Exception('Any exception.  E.g., bad version or some other '
                      'non-Manila Exception.'))
        self.assertRaises(exception.ManilaException, self.mediator.do_setup)

    def test_mediator_setup_client_ssh_error(self):

        # This could be anything the client comes up with, but the
        # mediator should turn it into a ManilaException.
        non_manila_exception = Exception('non-manila-except')
        self.mock_client.setSSHOptions.side_effect = non_manila_exception

        self.assertRaises(exception.ManilaException, self.mediator.do_setup)
        self.mock_client.assert_has_calls(
            [mock.call.setSSHOptions(constants.EXPECTED_IP_1234,
                                     constants.SAN_LOGIN,
                                     constants.SAN_PASSWORD,
                                     port=constants.PORT,
                                     conn_timeout=constants.TIMEOUT)])

    def test_mediator_vfs_exception(self):
        """Backend exception during get_vfs_name."""

        self.mediator.do_setup()
        self.mock_client.getvfs.side_effect = Exception('non-manila-except')
        self.assertRaises(exception.ManilaException,
                          self.mediator.get_vfs_name,
                          fpg=constants.EXPECTED_FPG)
        expected_calls = [
            mock.call.getvfs(fpg=constants.EXPECTED_FPG, vfs=None),
        ]
        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_vfs_not_found(self):
        """VFS not found."""
        self.mediator.do_setup()
        self.mock_client.getvfs.return_value = {'total': 0}
        self.assertRaises(exception.ManilaException,
                          self.mediator.get_vfs_name,
                          fpg=constants.EXPECTED_FPG)
        expected_calls = [
            mock.call.getvfs(fpg=constants.EXPECTED_FPG, vfs=None),
        ]
        self.mock_client.assert_has_calls(expected_calls)

    def init_mediator(self):
        """Basic mediator setup for re-use with tests that need one."""

        self.mock_client.getvfs.return_value = {
            'total': 1,
            'members': [{'vfsname': constants.EXPECTED_VFS}]
        }
        self.mock_client.getfshare.return_value = {
            'total': 1,
            'members': [
                {'fstoreName': constants.EXPECTED_FSTORE,
                 'shareName': constants.EXPECTED_SHARE_ID,
                 'shareDir': constants.EXPECTED_SHARE_PATH,
                 'sharePath': constants.EXPECTED_SHARE_PATH}]
        }
        self.mediator.do_setup()

    def test_mediator_setup_success(self):
        """Do a mediator setup without errors."""

        self.init_mediator()
        self.assertIsNotNone(self.mediator._client)

        expected_calls = [
            mock.call.setSSHOptions(constants.EXPECTED_IP_1234,
                                    constants.SAN_LOGIN,
                                    constants.SAN_PASSWORD,
                                    port=constants.PORT,
                                    conn_timeout=constants.TIMEOUT),
            mock.call.ssh.set_debug_flag(constants.EXPECTED_HP_DEBUG)
        ]
        self.mock_client.assert_has_calls(expected_calls)

    def get_expected_calls_for_create_share(self,
                                            expected_fpg,
                                            expected_vfsname,
                                            expected_protocol,
                                            expected_project_id,
                                            expected_share_id):
        expected_sharedir = expected_share_id

        if expected_protocol == constants.NFS_LOWER:
            expected_calls = [
                mock.call.createfstore(expected_vfsname, expected_project_id,
                                       comment='OpenStack Manila fstore',
                                       fpg=expected_fpg),
                mock.call.getfsquota(fpg=expected_fpg,
                                     vfs=expected_vfsname,
                                     fstore=expected_project_id),
                mock.call.setfsquota(expected_vfsname,
                                     fpg=expected_fpg,
                                     hcapacity='2048',
                                     scapacity='2048',
                                     fstore=expected_project_id),
                mock.call.createfshare(expected_protocol, expected_vfsname,
                                       expected_share_id,
                                       comment='OpenStack Manila fshare',
                                       fpg=expected_fpg,
                                       sharedir=expected_sharedir,
                                       clientip='127.0.0.1',
                                       options='rw,no_root_squash,insecure',
                                       fstore=expected_project_id),
                mock.call.getfshare(expected_protocol, expected_share_id,
                                    fpg=expected_fpg, vfs=expected_vfsname,
                                    fstore=expected_project_id)]
        else:
            expected_calls = [
                mock.call.createfstore(expected_vfsname, expected_project_id,
                                       comment='OpenStack Manila fstore',
                                       fpg=expected_fpg),
                mock.call.getfsquota(fpg=expected_fpg,
                                     vfs=expected_vfsname,
                                     fstore=expected_project_id),
                mock.call.setfsquota(expected_vfsname,
                                     fpg=expected_fpg,
                                     hcapacity='2048',
                                     scapacity='2048',
                                     fstore=expected_project_id),
                mock.call.createfshare(expected_protocol, expected_vfsname,
                                       expected_share_id,
                                       comment='OpenStack Manila fshare',
                                       fpg=expected_fpg,
                                       sharedir=expected_sharedir,
                                       allowip='127.0.0.1',
                                       fstore=expected_project_id),
                mock.call.getfshare(expected_protocol, expected_share_id,
                                    fpg=expected_fpg, vfs=expected_vfsname,
                                    fstore=expected_project_id)]
        return expected_calls

    def test_mediator_create_cifs_share(self):
        self.init_mediator()

        self.mock_client.getfshare.return_value = {
            'message': None,
            'total': 1,
            'members': [{'shareName': constants.EXPECTED_SHARE_NAME}]
        }

        self.mock_client.getfsquota.return_value = {
            'message': None,
            'total': 1,
            'members': [{'hardBlock': '1024', 'softBlock': '1024'}]
        }

        location = self.mediator.create_share(constants.EXPECTED_PROJECT_ID,
                                              constants.EXPECTED_SHARE_ID,
                                              constants.CIFS,
                                              constants.EXPECTED_FPG,
                                              constants.EXPECTED_VFS,
                                              size=constants.EXPECTED_SIZE_1)

        self.assertEqual(constants.EXPECTED_SHARE_NAME, location)

        expected_calls = self.get_expected_calls_for_create_share(
            constants.EXPECTED_FPG,
            constants.EXPECTED_VFS,
            constants.SMB_LOWER,
            constants.EXPECTED_PROJECT_ID,
            constants.EXPECTED_SHARE_ID)

        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_create_nfs_share(self):
        self.init_mediator()

        self.mock_client.getfshare.return_value = {
            'message': None,
            'total': 1,
            'members': [{'sharePath': constants.EXPECTED_SHARE_PATH}]
        }

        self.mock_client.getfsquota.return_value = {
            'message': None,
            'total': 1,
            'members': [{'hardBlock': '1024', 'softBlock': '1024'}]
        }

        location = self.mediator.create_share(constants.EXPECTED_PROJECT_ID,
                                              constants.EXPECTED_SHARE_ID,
                                              constants.NFS.lower(),
                                              constants.EXPECTED_FPG,
                                              constants.EXPECTED_VFS,
                                              size=constants.EXPECTED_SIZE_1)

        self.assertEqual(constants.EXPECTED_SHARE_PATH, location)

        expected_calls = self.get_expected_calls_for_create_share(
            constants.EXPECTED_FPG,
            constants.EXPECTED_VFS,
            constants.NFS.lower(),
            constants.EXPECTED_PROJECT_ID,
            constants.EXPECTED_SHARE_ID)

        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_create_cifs_share_from_snapshot(self):
        self.init_mediator()

        self.mock_client.getfsnap.return_value = {
            'message': None,
            'total': 1,
            'members': [{'snapName': constants.EXPECTED_SNAP_ID,
                         'fstoreName': constants.EXPECTED_FSTORE}]
        }

        location = self.mediator.create_share_from_snapshot(
            constants.EXPECTED_SHARE_ID,
            constants.CIFS,
            constants.EXPECTED_PROJECT_ID,
            constants.EXPECTED_SHARE_ID,
            constants.NFS,
            constants.EXPECTED_SNAP_ID,
            constants.EXPECTED_FPG,
            constants.EXPECTED_VFS)

        self.assertEqual(constants.EXPECTED_SHARE_ID, location)

        expected_calls = [
            mock.call.getfsnap('*_%s' % constants.EXPECTED_SNAP_ID,
                               vfs=constants.EXPECTED_VFS,
                               fpg=constants.EXPECTED_FPG,
                               pat=True,
                               fstore=constants.EXPECTED_FSTORE),
            mock.call.createfshare(constants.SMB_LOWER,
                                   constants.EXPECTED_VFS,
                                   constants.EXPECTED_SHARE_ID,
                                   comment=mock.ANY,
                                   fpg=constants.EXPECTED_FPG,
                                   sharedir='.snapshot/%s/%s' % (
                                            constants.EXPECTED_SNAP_ID,
                                            constants.EXPECTED_SHARE_ID),
                                   fstore=constants.EXPECTED_FSTORE,
                                   allowip=constants.EXPECTED_IP_127),
            mock.call.getfshare(constants.SMB_LOWER,
                                constants.EXPECTED_SHARE_ID,
                                fpg=constants.EXPECTED_FPG,
                                vfs=constants.EXPECTED_VFS,
                                fstore=constants.EXPECTED_FSTORE)]

        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_create_nfs_share_from_snapshot(self):
        self.init_mediator()

        self.mock_client.getfsnap.return_value = {
            'message': None,
            'total': 1,
            'members': [{'snapName': constants.EXPECTED_SNAP_ID,
                         'fstoreName': constants.EXPECTED_FSTORE}]
        }

        location = self.mediator.create_share_from_snapshot(
            constants.EXPECTED_SHARE_ID,
            constants.NFS,
            constants.EXPECTED_PROJECT_ID,
            constants.EXPECTED_SHARE_ID,
            constants.NFS,
            constants.EXPECTED_SNAP_ID,
            constants.EXPECTED_FPG,
            constants.EXPECTED_VFS)

        self.assertEqual(constants.EXPECTED_SHARE_PATH, location)

        expected_calls = [
            mock.call.getfsnap('*_%s' % constants.EXPECTED_SNAP_ID,
                               vfs=constants.EXPECTED_VFS,
                               fpg=constants.EXPECTED_FPG,
                               pat=True,
                               fstore=constants.EXPECTED_FSTORE),
            mock.call.createfshare(constants.NFS_LOWER,
                                   constants.EXPECTED_VFS,
                                   constants.EXPECTED_SHARE_ID,
                                   comment=mock.ANY,
                                   fpg=constants.EXPECTED_FPG,
                                   sharedir='.snapshot/%s/%s' %
                                            (constants.EXPECTED_SNAP_ID,
                                             constants.EXPECTED_SHARE_ID),
                                   fstore=constants.EXPECTED_FSTORE,
                                   clientip=constants.EXPECTED_IP_127,
                                   options='ro,no_root_squash,insecure'),
            mock.call.getfshare(constants.NFS_LOWER,
                                constants.EXPECTED_SHARE_ID,
                                fpg=constants.EXPECTED_FPG,
                                vfs=constants.EXPECTED_VFS,
                                fstore=constants.EXPECTED_FSTORE)]

        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_create_share_from_snap_not_found(self):
        self.init_mediator()

        self.mock_client.getfsnap.return_value = {
            'message': None,
            'total': 0,
            'members': []
        }

        self.assertRaises(exception.ShareBackendException,
                          self.mediator.create_share_from_snapshot,
                          constants.EXPECTED_SHARE_ID,
                          constants.NFS,
                          constants.EXPECTED_PROJECT_ID,
                          constants.EXPECTED_SHARE_ID,
                          constants.NFS,
                          constants.EXPECTED_SNAP_ID,
                          constants.EXPECTED_FPG,
                          constants.EXPECTED_VFS)

    def test_mediator_delete_share(self):
        self.init_mediator()

        self.mock_object(self.mediator,
                         '_find_fstore',
                         mock.Mock(return_value=constants.EXPECTED_SHARE_ID))

        self.mediator.delete_share(constants.EXPECTED_PROJECT_ID,
                                   constants.EXPECTED_SHARE_ID,
                                   constants.CIFS,
                                   constants.EXPECTED_FPG,
                                   constants.EXPECTED_VFS)

        expected_calls = [
            mock.call.removefshare(constants.SMB_LOWER,
                                   constants.EXPECTED_VFS,
                                   constants.EXPECTED_SHARE_ID,
                                   fpg=constants.EXPECTED_FPG,
                                   fstore=constants.EXPECTED_SHARE_ID),
            mock.call.removefstore(constants.EXPECTED_VFS,
                                   constants.EXPECTED_SHARE_ID,
                                   fpg=constants.EXPECTED_FPG),
        ]

        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_create_snapshot(self):
        self.init_mediator()

        self.mediator.create_snapshot(constants.EXPECTED_PROJECT_ID,
                                      constants.EXPECTED_SHARE_ID,
                                      constants.NFS,
                                      constants.EXPECTED_SNAP_NAME,
                                      constants.EXPECTED_FPG,
                                      constants.EXPECTED_VFS)

        expected_calls = [
            mock.call.createfsnap(constants.EXPECTED_VFS,
                                  constants.EXPECTED_PROJECT_ID,
                                  constants.EXPECTED_SNAP_NAME,
                                  fpg=constants.EXPECTED_FPG)
        ]
        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_create_snapshot_backend_exception(self):
        self.init_mediator()

        # createfsnap exception
        self.mock_client.createfsnap.side_effect = Exception(
            'createfsnap fail.')

        self.assertRaises(exception.ShareBackendException,
                          self.mediator.create_snapshot,
                          constants.EXPECTED_PROJECT_ID,
                          constants.EXPECTED_SHARE_ID,
                          constants.NFS,
                          constants.EXPECTED_SNAP_NAME,
                          constants.EXPECTED_FPG,
                          constants.EXPECTED_VFS)

    def test_mediator_delete_snapshot(self):
        self.init_mediator()

        expected_name_from_array = 'name-from-array'

        self.mock_client.getfsnap.return_value = {
            'total': 1,
            'members': [
                {
                    'snapName': expected_name_from_array,
                    'fstoreName': constants.EXPECTED_PROJECT_ID,
                }
            ],
            'message': None
        }

        self.mock_client.getfshare.side_effect = [
            # some typical independent NFS share (path) and SMB share (dir)
            {
                'total': 1,
                'members': [{'sharePath': '/anyfpg/anyvfs/anyfstore'}]
            },
            {
                'total': 1,
                'members': [{'shareDir': []}],
            }
        ]

        self.mediator.delete_snapshot(constants.EXPECTED_PROJECT_ID,
                                      constants.EXPECTED_SHARE_ID,
                                      constants.NFS,
                                      constants.EXPECTED_SNAP_NAME,
                                      constants.EXPECTED_FPG,
                                      constants.EXPECTED_VFS)

        expected_calls = [
            mock.call.getfsnap('*_%s' % constants.EXPECTED_SNAP_NAME,
                               vfs=constants.EXPECTED_VFS,
                               fpg=constants.EXPECTED_FPG,
                               pat=True,
                               fstore=constants.EXPECTED_PROJECT_ID),
            mock.call.getfshare(constants.NFS_LOWER,
                                fpg=constants.EXPECTED_FPG,
                                vfs=constants.EXPECTED_VFS,
                                fstore=constants.EXPECTED_PROJECT_ID),
            mock.call.getfshare(constants.SMB_LOWER,
                                fpg=constants.EXPECTED_FPG,
                                vfs=constants.EXPECTED_VFS,
                                fstore=constants.EXPECTED_PROJECT_ID),
            mock.call.removefsnap(constants.EXPECTED_VFS,
                                  constants.EXPECTED_PROJECT_ID,
                                  fpg=constants.EXPECTED_FPG,
                                  snapname=expected_name_from_array),
            mock.call.startfsnapclean(constants.EXPECTED_FPG,
                                      reclaimStrategy='maxspeed')
        ]
        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_delete_snapshot_not_found(self):
        self.init_mediator()

        self.mock_client.getfsnap.return_value = {
            'total': 0,
            'members': [],
        }

        self.mediator.delete_snapshot(constants.EXPECTED_PROJECT_ID,
                                      constants.EXPECTED_SHARE_ID,
                                      constants.NFS,
                                      constants.EXPECTED_SNAP_NAME,
                                      constants.EXPECTED_FPG,
                                      constants.EXPECTED_VFS)

        expected_calls = [
            mock.call.getfsnap('*_%s' % constants.EXPECTED_SNAP_NAME,
                               vfs=constants.EXPECTED_VFS,
                               fpg=constants.EXPECTED_FPG,
                               pat=True,
                               fstore=constants.EXPECTED_SHARE_ID),
        ]

        # Code coverage for early exit when nothing to delete.
        self.mock_client.assert_has_calls(expected_calls)
        self.assertFalse(self.mock_client.getfshare.called)
        self.assertFalse(self.mock_client.removefsnap.called)
        self.assertFalse(self.mock_client.startfsnapclean.called)

    def test_mediator_delete_snapshot_shared_nfs(self):
        self.init_mediator()

        # Mock a share under this snapshot for NFS
        snapshot_dir = '.snapshot/DT_%s' % constants.EXPECTED_SNAP_NAME
        snapshot_path = '%s/%s' % (constants.EXPECTED_SHARE_PATH, snapshot_dir)

        self.mock_client.getfsnap.return_value = {
            'total': 1,
            'members': [{'snapName': constants.EXPECTED_SNAP_NAME}]
        }

        self.mock_client.getfshare.side_effect = [
            # some typical independent NFS share (path) and SMB share (dir)
            {
                'total': 1,
                'members': [{'sharePath': snapshot_path}],
            },
            {
                'total': 0,
                'members': [],
            }
        ]

        self.assertRaises(exception.Invalid,
                          self.mediator.delete_snapshot,
                          constants.EXPECTED_PROJECT_ID,
                          constants.EXPECTED_SHARE_ID,
                          constants.NFS,
                          constants.EXPECTED_SNAP_NAME,
                          constants.EXPECTED_FPG,
                          constants.EXPECTED_VFS)

    def test_mediator_delete_snapshot_shared_smb(self):
        self.init_mediator()

        # Mock a share under this snapshot for SMB
        snapshot_dir = '.snapshot/DT_%s' % constants.EXPECTED_SNAP_NAME

        self.mock_client.getfsnap.return_value = {
            'total': 1,
            'members': [{'snapName': constants.EXPECTED_SNAP_NAME}]
        }

        self.mock_client.getfshare.side_effect = [
            # some typical independent NFS share (path) and SMB share (dir)
            {
                'total': 1,
                'members': [{'sharePath': constants.EXPECTED_SHARE_PATH}],
            },
            {
                'total': 1,
                'members': [{'shareDir': snapshot_dir}],
            }
        ]

        self.assertRaises(exception.Invalid,
                          self.mediator.delete_snapshot,
                          constants.EXPECTED_PROJECT_ID,
                          constants.EXPECTED_SHARE_ID,
                          constants.NFS,
                          constants.EXPECTED_SNAP_NAME,
                          constants.EXPECTED_FPG,
                          constants.EXPECTED_VFS)

    def _assert_delete_snapshot_raises(self):
        self.assertRaises(exception.ShareBackendException,
                          self.mediator.delete_snapshot,
                          constants.EXPECTED_PROJECT_ID,
                          constants.EXPECTED_SHARE_ID,
                          constants.NFS,
                          constants.EXPECTED_SNAP_NAME,
                          constants.EXPECTED_FPG,
                          constants.EXPECTED_VFS)

    def test_mediator_delete_snapshot_backend_exceptions(self):
        self.init_mediator()

        # getfsnap exception
        self.mock_client.getfsnap.side_effect = Exception('getfsnap fail.')
        self._assert_delete_snapshot_raises()

        # getfsnap OK
        self.mock_client.getfsnap.side_effect = None
        self.mock_client.getfsnap.return_value = {
            'total': 1,
            'members': [{'snapName': constants.EXPECTED_SNAP_NAME,
                         'fstoreName': constants.EXPECTED_FSTORE}]
        }

        # getfshare exception
        self.mock_client.getfshare.side_effect = Exception('getfshare fail.')
        self._assert_delete_snapshot_raises()

        # getfshare OK
        def mock_fshare(*args, **kwargs):
            if args[0] == constants.NFS_LOWER:
                return {
                    'total': 1,
                    'members': [{'sharePath': '/anyfpg/anyvfs/anyfstore',
                                 'fstoreName': constants.EXPECTED_FSTORE}]
                }
            else:
                return {
                    'total': 1,
                    'members': [{'shareDir': [],
                                 'fstoreName': constants.EXPECTED_FSTORE}]
                }

        self.mock_client.getfshare.side_effect = mock_fshare

        # removefsnap exception
        self.mock_client.removefsnap.side_effect = Exception(
            'removefsnap fail.')
        self._assert_delete_snapshot_raises()

        # removefsnap OK
        self.mock_client.removefsnap.side_effect = None
        self.mock_client.removefsnap.return_value = []

        # startfsnapclean exception (logged, not raised)
        self.mock_client.startfsnapclean.side_effect = Exception(
            'startfsnapclean fail.')
        mock_log = self.mock_object(hp3parmediator, 'LOG')

        self.mediator.delete_snapshot(constants.EXPECTED_PROJECT_ID,
                                      constants.EXPECTED_SHARE_ID,
                                      constants.NFS,
                                      constants.EXPECTED_SNAP_NAME,
                                      constants.EXPECTED_FPG,
                                      constants.EXPECTED_VFS)

        expected_calls = [
            mock.call.getfsnap('*_%s' % constants.EXPECTED_SNAP_NAME,
                               vfs=constants.EXPECTED_VFS,
                               fpg=constants.EXPECTED_FPG,
                               pat=True,
                               fstore=constants.EXPECTED_FSTORE),
            mock.call.getfshare(constants.NFS_LOWER,
                                fpg=constants.EXPECTED_FPG,
                                vfs=constants.EXPECTED_VFS,
                                fstore=constants.EXPECTED_FSTORE),
            mock.call.getfshare(constants.SMB_LOWER,
                                fpg=constants.EXPECTED_FPG,
                                vfs=constants.EXPECTED_VFS,
                                fstore=constants.EXPECTED_FSTORE),
            mock.call.removefsnap(constants.EXPECTED_VFS,
                                  constants.EXPECTED_FSTORE,
                                  fpg=constants.EXPECTED_FPG,
                                  snapname=constants.EXPECTED_SNAP_NAME),
            mock.call.startfsnapclean(constants.EXPECTED_FPG,
                                      reclaimStrategy='maxspeed'),
        ]
        self.mock_client.assert_has_calls(expected_calls)
        mock_log.assert_has_calls(mock.call.exception(mock.ANY))

    def test_mediator_get_capacity(self):
        """Mediator converts client stats to capacity result."""
        expected_capacity = constants.EXPECTED_SIZE_2
        expected_free = constants.EXPECTED_SIZE_1

        self.init_mediator()
        self.mock_client.getfpg.return_value = {
            'total': 1,
            'members': [
                {
                    'capacityKiB': str(expected_capacity * units.Mi),
                    'availCapacityKiB': str(expected_free * units.Mi)
                }
            ],
            'message': None,
        }

        expected_result = {
            'free_capacity_gb': expected_free,
            'total_capacity_gb': expected_capacity,
        }

        result = self.mediator.get_capacity(constants.EXPECTED_FPG)
        self.assertEqual(expected_result, result)
        expected_calls = [
            mock.call.getfpg(constants.EXPECTED_FPG)
        ]
        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_allow_user_access_cifs(self):
        """"Allow user access to cifs share."""
        self.init_mediator()

        expected_allowperm = '+%s:fullcontrol' % constants.USERNAME

        self.mediator.allow_access(constants.EXPECTED_PROJECT_ID,
                                   constants.EXPECTED_SHARE_ID,
                                   constants.CIFS,
                                   constants.USER,
                                   constants.USERNAME,
                                   constants.EXPECTED_FPG,
                                   constants.EXPECTED_VFS)

        expected_calls = [
            mock.call.setfshare(constants.SMB_LOWER,
                                constants.EXPECTED_VFS,
                                constants.EXPECTED_SHARE_ID,
                                allowperm=expected_allowperm,
                                fpg=constants.EXPECTED_FPG,
                                fstore=constants.EXPECTED_FSTORE)

        ]
        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_deny_user_access_cifs(self):
        """"Deny user access to cifs share."""
        self.init_mediator()

        expected_denyperm = '-%s:fullcontrol' % constants.USERNAME

        self.mediator.deny_access(constants.EXPECTED_PROJECT_ID,
                                  constants.EXPECTED_SHARE_ID,
                                  constants.CIFS,
                                  constants.USER,
                                  constants.USERNAME,
                                  constants.EXPECTED_FPG,
                                  constants.EXPECTED_VFS)

        expected_calls = [
            mock.call.setfshare(constants.SMB_LOWER,
                                constants.EXPECTED_VFS,
                                constants.EXPECTED_SHARE_ID,
                                allowperm=expected_denyperm,
                                fpg=constants.EXPECTED_FPG,
                                fstore=constants.EXPECTED_FSTORE)

        ]
        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_allow_ip_access_cifs(self):
        """"Allow ip access to cifs share."""
        self.init_mediator()

        expected_allowip = '+%s' % constants.EXPECTED_IP_1234

        self.mediator.allow_access(constants.EXPECTED_PROJECT_ID,
                                   constants.EXPECTED_SHARE_ID,
                                   constants.CIFS,
                                   constants.IP,
                                   constants.EXPECTED_IP_1234,
                                   constants.EXPECTED_FPG,
                                   constants.EXPECTED_VFS)

        expected_calls = [
            mock.call.setfshare(constants.SMB_LOWER,
                                constants.EXPECTED_VFS,
                                constants.EXPECTED_SHARE_ID,
                                allowip=expected_allowip,
                                fpg=constants.EXPECTED_FPG,
                                fstore=constants.EXPECTED_FSTORE)
        ]
        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_deny_ip_access_cifs(self):
        """"Deny ip access to cifs share."""
        self.init_mediator()

        expected_denyip = '-%s' % constants.EXPECTED_IP_1234

        self.mediator.deny_access(constants.EXPECTED_PROJECT_ID,
                                  constants.EXPECTED_SHARE_ID,
                                  constants.CIFS,
                                  constants.IP,
                                  constants.EXPECTED_IP_1234,
                                  constants.EXPECTED_FPG,
                                  constants.EXPECTED_VFS)

        expected_calls = [
            mock.call.setfshare(constants.SMB_LOWER,
                                constants.EXPECTED_VFS,
                                constants.EXPECTED_SHARE_ID,
                                allowip=expected_denyip,
                                fpg=constants.EXPECTED_FPG,
                                fstore=constants.EXPECTED_FSTORE)
        ]
        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_allow_ip_access_nfs(self):
        """"Allow ip access to nfs share."""
        self.init_mediator()

        expected_clientip = '+%s' % constants.EXPECTED_IP_1234

        self.mediator.allow_access(constants.EXPECTED_PROJECT_ID,
                                   constants.EXPECTED_SHARE_ID,
                                   constants.NFS,
                                   constants.IP,
                                   constants.EXPECTED_IP_1234,
                                   constants.EXPECTED_FPG,
                                   constants.EXPECTED_VFS)

        expected_calls = [
            mock.call.setfshare(constants.NFS.lower(),
                                constants.EXPECTED_VFS,
                                constants.EXPECTED_SHARE_ID,
                                clientip=expected_clientip,
                                fpg=constants.EXPECTED_FPG,
                                fstore=constants.EXPECTED_FSTORE)
        ]
        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_deny_ip_access_nfs(self):
        """"Deny ip access to nfs share."""
        self.init_mediator()

        expected_clientip = '-%s' % constants.EXPECTED_IP_1234

        self.mediator.deny_access(constants.EXPECTED_PROJECT_ID,
                                  constants.EXPECTED_SHARE_ID,
                                  constants.NFS,
                                  constants.IP,
                                  constants.EXPECTED_IP_1234,
                                  constants.EXPECTED_FPG,
                                  constants.EXPECTED_VFS)

        expected_calls = [
            mock.call.setfshare(constants.NFS.lower(),
                                constants.EXPECTED_VFS,
                                constants.EXPECTED_SHARE_ID,
                                clientip=expected_clientip,
                                fpg=constants.EXPECTED_FPG,
                                fstore=constants.EXPECTED_FSTORE)
        ]
        self.mock_client.assert_has_calls(expected_calls)

    def test_mediator_allow_user_access_nfs(self):
        """"Allow user access to nfs share is not supported."""
        self.init_mediator()

        self.assertRaises(exception.HP3ParInvalid,
                          self.mediator.allow_access,
                          constants.EXPECTED_PROJECT_ID,
                          constants.EXPECTED_SHARE_ID,
                          constants.NFS,
                          constants.USER,
                          constants.USERNAME,
                          constants.EXPECTED_FPG,
                          constants.EXPECTED_VFS)

    def test_mediator_allow_access_bad_proto(self):
        """"Allow user access to unsupported protocol."""
        self.init_mediator()

        self.assertRaises(exception.InvalidInput,
                          self.mediator.allow_access,
                          constants.EXPECTED_PROJECT_ID,
                          constants.EXPECTED_SHARE_ID,
                          'unsupported_other_protocol',
                          constants.USER,
                          constants.USERNAME,
                          constants.EXPECTED_FPG,
                          constants.EXPECTED_VFS)

    def test_mediator_allow_access_bad_type(self):
        """"Allow user access to unsupported access type."""
        self.init_mediator()

        self.assertRaises(exception.InvalidInput,
                          self.mediator.allow_access,
                          constants.EXPECTED_PROJECT_ID,
                          constants.EXPECTED_SHARE_ID,
                          constants.CIFS,
                          'unsupported_other_type',
                          constants.USERNAME,
                          constants.EXPECTED_FPG,
                          constants.EXPECTED_VFS)

    @ddt.data((('nfs', 'NFS', 'nFs'), 'smb'),
              (('smb', 'SMB', 'SmB', 'CIFS', 'cifs', 'CiFs'), 'nfs'))
    @ddt.unpack
    def test_other_protocol(self, protocols, expected_other):
        for protocol in protocols:
            self.assertEqual(expected_other,
                             hp3parmediator.HP3ParMediator().other_protocol(
                                 protocol))

    @ddt.data('', 'bogus')
    def test_other_protocol_exception(self, protocol):
        self.assertRaises(exception.InvalidInput,
                          hp3parmediator.HP3ParMediator().other_protocol,
                          protocol)

    @ddt.data(('osf-uid', None, 'osf-uid'),
              ('uid', None, 'osf-uid'),
              ('uid', 'smb', 'osf-smb-uid'),
              ('uid', 'smb', 'osf-smb-uid'))
    @ddt.unpack
    def test_ensure_prefix(self, uid, protocol, expected):
        self.assertEqual(expected,
                         hp3parmediator.HP3ParMediator().ensure_prefix(
                             uid, protocol=protocol))

    def test_find_fstore_search(self):
        self.init_mediator()

        mock_find_fshare = self.mock_object(self.mediator,
                                            '_find_fshare',
                                            mock.Mock(return_value=None))

        result = self.mediator._find_fstore(constants.EXPECTED_PROJECT_ID,
                                            constants.EXPECTED_SHARE_ID,
                                            constants.NFS,
                                            constants.EXPECTED_FPG,
                                            constants.EXPECTED_VFS)

        mock_find_fshare.assert_called_once_with(constants.EXPECTED_PROJECT_ID,
                                                 constants.EXPECTED_SHARE_ID,
                                                 constants.NFS,
                                                 constants.EXPECTED_FPG,
                                                 constants.EXPECTED_VFS)
        self.assertIsNone(result)

    def test_find_fstore_search_xproto(self):
        self.init_mediator()

        mock_find_fshare = self.mock_object(self.mediator,
                                            '_find_fshare',
                                            mock.Mock(return_value=None))

        result = self.mediator._find_fstore(constants.EXPECTED_PROJECT_ID,
                                            constants.EXPECTED_SHARE_ID,
                                            constants.NFS,
                                            constants.EXPECTED_FPG,
                                            constants.EXPECTED_VFS,
                                            allow_cross_protocol=True)

        expected_calls = [
            mock.call(constants.EXPECTED_PROJECT_ID,
                      constants.EXPECTED_SHARE_ID,
                      constants.NFS,
                      constants.EXPECTED_FPG,
                      constants.EXPECTED_VFS),
            mock.call(constants.EXPECTED_PROJECT_ID,
                      constants.EXPECTED_SHARE_ID,
                      constants.SMB_LOWER,
                      constants.EXPECTED_FPG,
                      constants.EXPECTED_VFS),
        ]
        mock_find_fshare.assert_has_calls(expected_calls)
        self.assertIsNone(result)

    def test_find_fshare_search(self):
        self.init_mediator()

        self.mock_client.getfshare.return_value = {}

        result = self.mediator._find_fshare(constants.EXPECTED_PROJECT_ID,
                                            constants.EXPECTED_SHARE_ID,
                                            constants.NFS,
                                            constants.EXPECTED_FPG,
                                            constants.EXPECTED_VFS)

        expected_calls = [
            mock.call.getfshare(constants.NFS_LOWER,
                                constants.EXPECTED_SHARE_ID,
                                fpg=constants.EXPECTED_FPG,
                                vfs=constants.EXPECTED_VFS,
                                fstore=constants.EXPECTED_PROJECT_ID),
            mock.call.getfshare(constants.NFS_LOWER,
                                constants.EXPECTED_SHARE_ID,
                                fpg=constants.EXPECTED_FPG,
                                vfs=constants.EXPECTED_VFS,
                                fstore=constants.EXPECTED_SHARE_ID),
            mock.call.getfshare(constants.NFS_LOWER,
                                constants.EXPECTED_SHARE_ID,
                                fpg=constants.EXPECTED_FPG),
            mock.call.getfshare(constants.NFS_LOWER,
                                constants.EXPECTED_SHARE_ID),
        ]
        self.mock_client.assert_has_calls(expected_calls)
        self.assertIsNone(result)

    def test_find_fshare_exception(self):
        self.init_mediator()

        self.mock_client.getfshare.side_effect = Exception('test unexpected')

        self.assertRaises(exception.ShareBackendException,
                          self.mediator._find_fshare,
                          constants.EXPECTED_PROJECT_ID,
                          constants.EXPECTED_SHARE_ID,
                          constants.NFS,
                          constants.EXPECTED_FPG,
                          constants.EXPECTED_VFS)

        self.mock_client.getfshare.assert_called_once_with(
            constants.NFS_LOWER,
            constants.EXPECTED_SHARE_ID,
            fpg=constants.EXPECTED_FPG,
            vfs=constants.EXPECTED_VFS,
            fstore=constants.EXPECTED_PROJECT_ID)

    def test_find_fshare_hit(self):
        self.init_mediator()

        expected_result = {'shareName': 'hit'}
        self.mock_client.getfshare.return_value = {
            'total': 1,
            'members': [expected_result]
        }

        result = self.mediator._find_fshare(constants.EXPECTED_PROJECT_ID,
                                            constants.EXPECTED_SHARE_ID,
                                            constants.NFS,
                                            constants.EXPECTED_FPG,
                                            constants.EXPECTED_VFS)

        self.mock_client.getfshare.assert_called_once_with(
            constants.NFS_LOWER,
            constants.EXPECTED_SHARE_ID,
            fpg=constants.EXPECTED_FPG,
            vfs=constants.EXPECTED_VFS,
            fstore=constants.EXPECTED_PROJECT_ID),
        self.assertEqual(expected_result, result)

    def test_find_fsnap_search(self):
        self.init_mediator()

        self.mock_client.getfsnap.return_value = {}

        result = self.mediator._find_fsnap(constants.EXPECTED_PROJECT_ID,
                                           constants.EXPECTED_SHARE_ID,
                                           constants.NFS,
                                           constants.EXPECTED_SNAP_ID,
                                           constants.EXPECTED_FPG,
                                           constants.EXPECTED_VFS)

        expected_snap_pattern = '*_%s' % constants.EXPECTED_SNAP_ID

        expected_calls = [
            mock.call.getfsnap(expected_snap_pattern,
                               vfs=constants.EXPECTED_VFS,
                               fpg=constants.EXPECTED_FPG,
                               pat=True,
                               fstore=constants.EXPECTED_PROJECT_ID),
            mock.call.getfsnap(expected_snap_pattern,
                               vfs=constants.EXPECTED_VFS,
                               fpg=constants.EXPECTED_FPG,
                               pat=True,
                               fstore=constants.EXPECTED_SHARE_ID),
            mock.call.getfsnap(expected_snap_pattern,
                               fpg=constants.EXPECTED_FPG,
                               pat=True),
            mock.call.getfsnap(expected_snap_pattern, pat=True),
        ]
        self.mock_client.assert_has_calls(expected_calls)
        self.assertIsNone(result)

    def test_find_fsnap_exception(self):
        self.init_mediator()

        self.mock_client.getfsnap.side_effect = Exception('test unexpected')

        self.assertRaises(exception.ShareBackendException,
                          self.mediator._find_fsnap,
                          constants.EXPECTED_PROJECT_ID,
                          constants.EXPECTED_SHARE_ID,
                          constants.NFS,
                          constants.EXPECTED_SNAP_ID,
                          constants.EXPECTED_FPG,
                          constants.EXPECTED_VFS)

        expected_snap_pattern = '*_%s' % constants.EXPECTED_SNAP_ID

        self.mock_client.getfsnap.assert_called_once_with(
            expected_snap_pattern,
            vfs=constants.EXPECTED_VFS,
            fpg=constants.EXPECTED_FPG,
            pat=True,
            fstore=constants.EXPECTED_PROJECT_ID)

    def test_find_fsnap_hit(self):
        self.init_mediator()

        expected_result = {'snapName': 'hit'}
        self.mock_client.getfsnap.return_value = {
            'total': 1,
            'members': [expected_result]
        }

        result = self.mediator._find_fsnap(constants.EXPECTED_PROJECT_ID,
                                           constants.EXPECTED_SHARE_ID,
                                           constants.NFS,
                                           constants.EXPECTED_SNAP_ID,
                                           constants.EXPECTED_FPG,
                                           constants.EXPECTED_VFS)

        expected_snap_pattern = '*_%s' % constants.EXPECTED_SNAP_ID

        self.mock_client.getfsnap.assert_called_once_with(
            expected_snap_pattern,
            vfs=constants.EXPECTED_VFS,
            fpg=constants.EXPECTED_FPG,
            pat=True,
            fstore=constants.EXPECTED_PROJECT_ID)

        self.assertEqual(expected_result, result)
