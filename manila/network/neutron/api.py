# Copyright 2013 OpenStack Foundation
# Copyright 2014 Mirantis Inc.
# All Rights Reserved
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

from neutronclient.common import exceptions as neutron_client_exc
from neutronclient.v2_0 import client as clientv20
from oslo_config import cfg
from oslo_log import log

from manila import context
from manila.db import base
from manila import exception
from manila.i18n import _LE
from manila.network.neutron import constants as neutron_constants

neutron_opts = [
    cfg.StrOpt(
        'neutron_url',
        default='http://127.0.0.1:9696',
        deprecated_group='DEFAULT',
        help='URL for connecting to neutron.'),
    cfg.IntOpt(
        'neutron_url_timeout',
        default=30,
        deprecated_group='DEFAULT',
        help='Timeout value for connecting to neutron in seconds.'),
    cfg.StrOpt(
        'neutron_admin_username',
        default='neutron',
        deprecated_group='DEFAULT',
        help='Username for connecting to neutron in admin context.'),
    cfg.StrOpt(
        'neutron_admin_password',
        help='Password for connecting to neutron in admin context.',
        deprecated_group='DEFAULT',
        secret=True),
    cfg.StrOpt(
        'neutron_admin_project_name',
        default='service',
        deprecated_group='DEFAULT',
        deprecated_name='neutron_admin_tenant_name',
        help='Project name for connecting to Neutron in admin context.'),
    cfg.StrOpt(
        'neutron_admin_auth_url',
        default='http://localhost:5000/v2.0',
        deprecated_group='DEFAULT',
        help='Auth URL for connecting to neutron in admin context.'),
    cfg.BoolOpt(
        'neutron_api_insecure',
        default=False,
        deprecated_group='DEFAULT',
        help='If set, ignore any SSL validation issues.'),
    cfg.StrOpt(
        'neutron_auth_strategy',
        default='keystone',
        deprecated_group='DEFAULT',
        help='Auth strategy for connecting to neutron in admin context.'),
    cfg.StrOpt(
        'neutron_ca_certificates_file',
        deprecated_group='DEFAULT',
        help='Location of CA certificates file to use for '
             'neutron client requests.'),
]

CONF = cfg.CONF
LOG = log.getLogger(__name__)


class API(base.Base):
    """API for interacting with the neutron 2.x API.

    :param configuration: instance of config or config group.
    """

    def __init__(self, config_group_name=None):
        super(API, self).__init__()
        self.config_group_name = config_group_name or 'DEFAULT'
        CONF.register_opts(neutron_opts, group=self.config_group_name)
        self.configuration = getattr(CONF, self.config_group_name, CONF)
        self.last_neutron_extension_sync = None
        self.extensions = {}
        self.client = self.get_client(context.get_admin_context())

    def _get_client(self, token=None):
        params = {
            'endpoint_url': self.configuration.neutron_url,
            'timeout': self.configuration.neutron_url_timeout,
            'insecure': self.configuration.neutron_api_insecure,
            'ca_cert': self.configuration.neutron_ca_certificates_file,
        }
        if token:
            params['token'] = token
            params['auth_strategy'] = None
        else:
            params['username'] = self.configuration.neutron_admin_username
            params['tenant_name'] = (
                self.configuration.neutron_admin_project_name)
            params['password'] = self.configuration.neutron_admin_password
            params['auth_url'] = self.configuration.neutron_admin_auth_url
            params['auth_strategy'] = self.configuration.neutron_auth_strategy
        return clientv20.Client(**params)

    def get_client(self, context):
        if context.is_admin:
            token = None
        elif not context.auth_token:
            raise neutron_client_exc.Unauthorized()
        else:
            token = context.auth_token
        return self._get_client(token=token)

    @property
    def admin_project_id(self):
        if self.client.httpclient.auth_token is None:
            try:
                self.client.httpclient.authenticate()
            except neutron_client_exc.NeutronClientException as e:
                raise exception.NetworkException(code=e.status_code,
                                                 message=e.message)
        return self.client.httpclient.auth_tenant_id

    def get_all_admin_project_networks(self):
        search_opts = {'tenant_id': self.admin_project_id, 'shared': False}
        nets = self.client.list_networks(**search_opts).get('networks', [])
        return nets

    def create_port(self, tenant_id, network_id, host_id=None, subnet_id=None,
                    fixed_ip=None, device_owner=None, device_id=None,
                    mac_address=None, security_group_ids=None, dhcp_opts=None):
        try:
            port_req_body = {'port': {}}
            port_req_body['port']['network_id'] = network_id
            port_req_body['port']['admin_state_up'] = True
            port_req_body['port']['tenant_id'] = tenant_id
            if security_group_ids:
                port_req_body['port']['security_groups'] = security_group_ids
            if mac_address:
                port_req_body['port']['mac_address'] = mac_address
            if self._has_port_binding_extension() and host_id:
                port_req_body['port']['binding:host_id'] = host_id
            if dhcp_opts is not None:
                port_req_body['port']['extra_dhcp_opts'] = dhcp_opts
            if subnet_id:
                fixed_ip_dict = {'subnet_id': subnet_id}
                if fixed_ip:
                    fixed_ip_dict.update({'ip_address': fixed_ip})
                port_req_body['port']['fixed_ips'] = [fixed_ip_dict]
            if device_owner:
                port_req_body['port']['device_owner'] = device_owner
            if device_id:
                port_req_body['port']['device_id'] = device_id
            port = self.client.create_port(port_req_body).get('port', {})
            return port
        except neutron_client_exc.NeutronClientException as e:
            LOG.exception(_LE('Neutron error creating port on network %s'),
                          network_id)
            if e.status_code == 409:
                raise exception.PortLimitExceeded()
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def delete_port(self, port_id):
        try:
            self.client.delete_port(port_id)
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def delete_subnet(self, subnet_id):
        try:
            self.client.delete_subnet(subnet_id)
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def list_ports(self, **search_opts):
        """List ports for the client based on search options."""
        return self.client.list_ports(**search_opts).get('ports')

    def show_port(self, port_id):
        """Return the port for the client given the port id."""
        try:
            return self.client.show_port(port_id).get('port')
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def get_all_networks(self):
        """Get all networks for client."""
        return self.client.list_networks().get('networks')

    def get_network(self, network_uuid):
        """Get specific network for client."""
        try:
            network = self.client.show_network(network_uuid).get('network', {})
            return network
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def get_subnet(self, subnet_uuid):
        """Get specific subnet for client."""
        try:
            return self.client.show_subnet(subnet_uuid).get('subnet', {})
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def list_extensions(self):
        extensions_list = self.client.list_extensions().get('extensions')
        return dict((ext['name'], ext) for ext in extensions_list)

    def _has_port_binding_extension(self):
        if not self.extensions:
            self.extensions = self.list_extensions()
        return neutron_constants.PORTBINDING_EXT in self.extensions

    def router_create(self, tenant_id, name):
        router_req_body = {'router': {}}
        router_req_body['router']['tenant_id'] = tenant_id
        router_req_body['router']['name'] = name
        try:
            return self.client.create_router(router_req_body).get('router', {})
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def network_create(self, tenant_id, name):
        network_req_body = {'network': {}}
        network_req_body['network']['tenant_id'] = tenant_id
        network_req_body['network']['name'] = name
        try:
            return self.client.create_network(
                network_req_body).get('network', {})
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def subnet_create(self, tenant_id, net_id, name, cidr):
        subnet_req_body = {'subnet': {}}
        subnet_req_body['subnet']['tenant_id'] = tenant_id
        subnet_req_body['subnet']['name'] = name
        subnet_req_body['subnet']['network_id'] = net_id
        subnet_req_body['subnet']['cidr'] = cidr
        subnet_req_body['subnet']['ip_version'] = 4
        try:
            return self.client.create_subnet(
                subnet_req_body).get('subnet', {})
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def router_add_interface(self, router_id, subnet_id, port_id=None):
        body = {}
        if subnet_id:
            body['subnet_id'] = subnet_id
        if port_id:
            body['port_id'] = port_id
        try:
            self.client.add_interface_router(router_id, body)
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def router_remove_interface(self, router_id, subnet_id, port_id=None):
        body = {}
        if subnet_id:
            body['subnet_id'] = subnet_id
        if port_id:
            body['port_id'] = port_id
        try:
            self.client.remove_interface_router(router_id, body)
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def router_list(self):
        try:
            return self.client.list_routers().get('routers', {})
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def update_port_fixed_ips(self, port_id, fixed_ips):
        try:
            port_req_body = {'port': fixed_ips}
            port = self.client.update_port(
                port_id, port_req_body).get('port', {})
            return port
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def show_router(self, router_id):
        try:
            return self.client.show_router(router_id).get('router', {})
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def router_update_routes(self, router_id, routes):
        try:
            router_req_body = {'router': routes}
            port = self.client.update_router(
                router_id, router_req_body).get('router', {})
            return port
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)

    def update_subnet(self, subnet_uuid, name):
        """Update specific subnet for client."""
        subnet_req_body = {'subnet': {'name': name}}
        try:
            return self.client.update_subnet(
                subnet_uuid, subnet_req_body).get('subnet', {})
        except neutron_client_exc.NeutronClientException as e:
            raise exception.NetworkException(code=e.status_code,
                                             message=e.message)
