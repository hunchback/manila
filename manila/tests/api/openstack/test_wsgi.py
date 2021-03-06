import ddt
import inspect
import webob

from manila.api.openstack import wsgi
from manila import exception
from manila import test
from manila.tests.api import fakes


@ddt.ddt
class RequestTest(test.TestCase):
    def test_content_type_missing(self):
        request = wsgi.Request.blank('/tests/123', method='POST')
        request.body = "<body />"
        self.assertEqual(None, request.get_content_type())

    def test_content_type_unsupported(self):
        request = wsgi.Request.blank('/tests/123', method='POST')
        request.headers["Content-Type"] = "text/html"
        request.body = "asdf<br />"
        self.assertRaises(exception.InvalidContentType,
                          request.get_content_type)

    def test_content_type_with_charset(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Content-Type"] = "application/json; charset=UTF-8"
        result = request.get_content_type()
        self.assertEqual(result, "application/json")

    def test_content_type_from_accept(self):
        content_type = 'application/json'
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = content_type

        result = request.best_match_content_type()

        self.assertEqual(result, content_type)

    def test_content_type_from_accept_best(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = "application/xml, application/json"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = ("application/json; q=0.3, "
                                     "application/xml; q=0.9")
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

    def test_content_type_from_query_extension(self):
        request = wsgi.Request.blank('/tests/123.json')
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

        request = wsgi.Request.blank('/tests/123.invalid')
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

    def test_content_type_accept_default(self):
        request = wsgi.Request.blank('/tests/123.unsupported')
        request.headers["Accept"] = "application/unsupported1"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

    def test_cache_and_retrieve_resources(self):
        request = wsgi.Request.blank('/foo')
        # Test that trying to retrieve a cached object on
        # an empty cache fails gracefully
        self.assertIsNone(request.cached_resource())
        self.assertIsNone(request.cached_resource_by_id('r-0'))

        resources = [{'id': 'r-%s' % x} for x in range(3)]

        # Cache an empty list of resources using the default name
        request.cache_resource([])
        self.assertEqual({}, request.cached_resource())
        self.assertIsNone(request.cached_resource('r-0'))
        # Cache some resources
        request.cache_resource(resources[:2])
        # Cache  one resource
        request.cache_resource(resources[2])
        # Cache  a different resource name
        other_resource = {'id': 'o-0'}
        request.cache_resource(other_resource, name='other-resource')

        self.assertEqual(resources[0], request.cached_resource_by_id('r-0'))
        self.assertEqual(resources[1], request.cached_resource_by_id('r-1'))
        self.assertEqual(resources[2], request.cached_resource_by_id('r-2'))
        self.assertIsNone(request.cached_resource_by_id('r-3'))
        self.assertEqual(
            {'r-0': resources[0], 'r-1': resources[1], 'r-2': resources[2]},
            request.cached_resource())
        self.assertEqual(
            other_resource,
            request.cached_resource_by_id('o-0', name='other-resource'))

    @ddt.data(
        'share_type',
    )
    def test_cache_and_retrieve_resources_by_resource(self, resource_name):
        cache_all_func = 'cache_db_%ss' % resource_name
        cache_one_func = 'cache_db_%s' % resource_name
        get_db_all_func = 'get_db_%ss' % resource_name
        get_db_one_func = 'get_db_%s' % resource_name

        r = wsgi.Request.blank('/foo')
        amount = 5
        res_range = range(amount)
        resources = [{'id': 'id%s' % x} for x in res_range]

        # Store 2
        getattr(r, cache_all_func)(resources[:amount - 1])
        # Store 1
        getattr(r, cache_one_func)(resources[amount - 1])

        for i in res_range:
            self.assertEqual(
                resources[i],
                getattr(r, get_db_one_func)('id%s' % i),
            )
        self.assertIsNone(getattr(r, get_db_one_func)('id%s' % amount))
        self.assertEqual(
            {'id%s' % i: resources[i] for i in res_range},
            getattr(r, get_db_all_func)())


class ActionDispatcherTest(test.TestCase):
    def test_dispatch(self):
        serializer = wsgi.ActionDispatcher()
        serializer.create = lambda x: 'pants'
        self.assertEqual(serializer.dispatch({}, action='create'), 'pants')

    def test_dispatch_action_None(self):
        serializer = wsgi.ActionDispatcher()
        serializer.create = lambda x: 'pants'
        serializer.default = lambda x: 'trousers'
        self.assertEqual(serializer.dispatch({}, action=None), 'trousers')

    def test_dispatch_default(self):
        serializer = wsgi.ActionDispatcher()
        serializer.create = lambda x: 'pants'
        serializer.default = lambda x: 'trousers'
        self.assertEqual(serializer.dispatch({}, action='update'), 'trousers')


class DictSerializerTest(test.TestCase):
    def test_dispatch_default(self):
        serializer = wsgi.DictSerializer()
        self.assertEqual(serializer.serialize({}, 'update'), '')


class JSONDictSerializerTest(test.TestCase):
    def test_json(self):
        input_dict = dict(servers=dict(a=(2, 3)))
        expected_json = '{"servers":{"a":[2,3]}}'
        serializer = wsgi.JSONDictSerializer()
        result = serializer.serialize(input_dict)
        result = result.replace('\n', '').replace(' ', '')
        self.assertEqual(result, expected_json)


class TextDeserializerTest(test.TestCase):
    def test_dispatch_default(self):
        deserializer = wsgi.TextDeserializer()
        self.assertEqual(deserializer.deserialize({}, 'update'), {})


class JSONDeserializerTest(test.TestCase):
    def test_json(self):
        data = """{"a": {
                "a1": "1",
                "a2": "2",
                "bs": ["1", "2", "3", {"c": {"c1": "1"}}],
                "d": {"e": "1"},
                "f": "1"}}"""
        as_dict = {
            'body': {
                'a': {
                    'a1': '1',
                    'a2': '2',
                    'bs': ['1', '2', '3', {'c': {'c1': '1'}}],
                    'd': {'e': '1'},
                    'f': '1',
                },
            },
        }
        deserializer = wsgi.JSONDeserializer()
        self.assertEqual(deserializer.deserialize(data), as_dict)


class ResourceTest(test.TestCase):
    def test_resource_call(self):
        class Controller(object):
            def index(self, req):
                return 'off'

        req = webob.Request.blank('/tests')
        app = fakes.TestRouter(Controller())
        response = req.get_response(app)
        self.assertEqual(response.body, 'off')
        self.assertEqual(response.status_int, 200)

    def test_resource_not_authorized(self):
        class Controller(object):
            def index(self, req):
                raise exception.NotAuthorized()

        req = webob.Request.blank('/tests')
        app = fakes.TestRouter(Controller())
        response = req.get_response(app)
        self.assertEqual(response.status_int, 403)

    def test_dispatch(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)
        method, extensions = resource.get_method(None, 'index', None, '')
        actual = resource.dispatch(method, None, {'pants': 'off'})
        expected = 'off'
        self.assertEqual(actual, expected)

    def test_get_method_undefined_controller_action(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)
        self.assertRaises(AttributeError, resource.get_method,
                          None, 'create', None, '')

    def test_get_method_action_json(self):
        class Controller(wsgi.Controller):
            @wsgi.action('fooAction')
            def _action_foo(self, req, id, body):
                return body

        controller = Controller()
        resource = wsgi.Resource(controller)
        method, extensions = resource.get_method(None, 'action',
                                                 'application/json',
                                                 '{"fooAction": true}')
        self.assertEqual(controller._action_foo, method)

    def test_get_method_action_bad_body(self):
        class Controller(wsgi.Controller):
            @wsgi.action('fooAction')
            def _action_foo(self, req, id, body):
                return body

        controller = Controller()
        resource = wsgi.Resource(controller)
        self.assertRaises(exception.MalformedRequestBody, resource.get_method,
                          None, 'action', 'application/json', '{}')

    def test_get_method_unknown_controller_action(self):
        class Controller(wsgi.Controller):
            @wsgi.action('fooAction')
            def _action_foo(self, req, id, body):
                return body

        controller = Controller()
        resource = wsgi.Resource(controller)
        self.assertRaises(KeyError, resource.get_method,
                          None, 'action', 'application/json',
                          '{"barAction": true}')

    def test_get_method_action_method(self):
        class Controller():
            def action(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)
        method, extensions = resource.get_method(None, 'action',
                                                 'application/xml',
                                                 '<fooAction>true</fooAction')
        self.assertEqual(controller.action, method)

    def test_get_action_args(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)

        env = {
            'wsgiorg.routing_args': [None, {
                'controller': None,
                'format': None,
                'action': 'update',
                'id': 12,
            }],
        }

        expected = {'action': 'update', 'id': 12}

        self.assertEqual(resource.get_action_args(env), expected)

    def test_get_body_bad_content(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)

        request = wsgi.Request.blank('/', method='POST')
        request.headers['Content-Type'] = 'application/none'
        request.body = 'foo'

        content_type, body = resource.get_body(request)
        self.assertEqual(content_type, None)
        self.assertEqual(body, '')

    def test_get_body_no_content_type(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)

        request = wsgi.Request.blank('/', method='POST')
        request.body = 'foo'

        content_type, body = resource.get_body(request)
        self.assertEqual(content_type, None)
        self.assertEqual(body, '')

    def test_get_body_no_content_body(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)

        request = wsgi.Request.blank('/', method='POST')
        request.headers['Content-Type'] = 'application/json'
        request.body = ''

        content_type, body = resource.get_body(request)
        self.assertEqual(content_type, None)
        self.assertEqual(body, '')

    def test_get_body(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)

        request = wsgi.Request.blank('/', method='POST')
        request.headers['Content-Type'] = 'application/json'
        request.body = 'foo'

        content_type, body = resource.get_body(request)
        self.assertEqual(content_type, 'application/json')
        self.assertEqual(body, 'foo')

    def test_deserialize_badtype(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)
        self.assertRaises(exception.InvalidContentType,
                          resource.deserialize,
                          controller.index, 'application/none', 'foo')

    def test_deserialize_default(self):
        class JSONDeserializer(object):
            def deserialize(self, body):
                return 'json'

        class XMLDeserializer(object):
            def deserialize(self, body):
                return 'xml'

        class Controller(object):
            @wsgi.deserializers(xml=XMLDeserializer)
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller, json=JSONDeserializer)

        obj = resource.deserialize(controller.index, 'application/json', 'foo')
        self.assertEqual(obj, 'json')

    def test_deserialize_decorator(self):
        class JSONDeserializer(object):
            def deserialize(self, body):
                return 'json'

        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller, json=JSONDeserializer)

        obj = resource.deserialize(controller.index, 'application/json', 'foo')
        self.assertEqual(obj, 'json')

    def test_register_actions(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        class ControllerExtended(wsgi.Controller):
            @wsgi.action('fooAction')
            def _action_foo(self, req, id, body):
                return body

            @wsgi.action('barAction')
            def _action_bar(self, req, id, body):
                return body

        controller = Controller()
        resource = wsgi.Resource(controller)
        self.assertEqual({}, resource.wsgi_actions)

        extended = ControllerExtended()
        resource.register_actions(extended)
        self.assertEqual({'fooAction': extended._action_foo,
                          'barAction': extended._action_bar, },
                         resource.wsgi_actions)

    def test_register_extensions(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        class ControllerExtended(wsgi.Controller):
            @wsgi.extends
            def index(self, req, resp_obj, pants=None):
                return None

            @wsgi.extends(action='fooAction')
            def _action_foo(self, req, resp, id, body):
                return None

        controller = Controller()
        resource = wsgi.Resource(controller)
        self.assertEqual({}, resource.wsgi_extensions)
        self.assertEqual({}, resource.wsgi_action_extensions)

        extended = ControllerExtended()
        resource.register_extensions(extended)
        self.assertEqual({'index': [extended.index]}, resource.wsgi_extensions)
        self.assertEqual({'fooAction': [extended._action_foo]},
                         resource.wsgi_action_extensions)

    def test_get_method_extensions(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        class ControllerExtended(wsgi.Controller):
            @wsgi.extends
            def index(self, req, resp_obj, pants=None):
                return None

        controller = Controller()
        extended = ControllerExtended()
        resource = wsgi.Resource(controller)
        resource.register_extensions(extended)
        method, extensions = resource.get_method(None, 'index', None, '')
        self.assertEqual(method, controller.index)
        self.assertEqual(extensions, [extended.index])

    def test_get_method_action_extensions(self):
        class Controller(wsgi.Controller):
            def index(self, req, pants=None):
                return pants

            @wsgi.action('fooAction')
            def _action_foo(self, req, id, body):
                return body

        class ControllerExtended(wsgi.Controller):
            @wsgi.extends(action='fooAction')
            def _action_foo(self, req, resp_obj, id, body):
                return None

        controller = Controller()
        extended = ControllerExtended()
        resource = wsgi.Resource(controller)
        resource.register_extensions(extended)
        method, extensions = resource.get_method(None, 'action',
                                                 'application/json',
                                                 '{"fooAction": true}')
        self.assertEqual(method, controller._action_foo)
        self.assertEqual(extensions, [extended._action_foo])

    def test_get_method_action_whitelist_extensions(self):
        class Controller(wsgi.Controller):
            def index(self, req, pants=None):
                return pants

        class ControllerExtended(wsgi.Controller):
            @wsgi.action('create')
            def _create(self, req, body):
                pass

            @wsgi.action('delete')
            def _delete(self, req, id):
                pass

        controller = Controller()
        extended = ControllerExtended()
        resource = wsgi.Resource(controller)
        resource.register_actions(extended)

        method, extensions = resource.get_method(None, 'create',
                                                 'application/json',
                                                 '{"create": true}')
        self.assertEqual(method, extended._create)
        self.assertEqual(extensions, [])

        method, extensions = resource.get_method(None, 'delete', None, None)
        self.assertEqual(method, extended._delete)
        self.assertEqual(extensions, [])

    def test_pre_process_extensions_regular(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)

        called = []

        def extension1(req, resp_obj):
            called.append(1)
            return None

        def extension2(req, resp_obj):
            called.append(2)
            return None

        extensions = [extension1, extension2]
        response, post = resource.pre_process_extensions(extensions, None, {})
        self.assertEqual(called, [])
        self.assertEqual(response, None)
        self.assertEqual(list(post), [extension2, extension1])

    def test_pre_process_extensions_generator(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)

        called = []

        def extension1(req):
            called.append('pre1')
            resp_obj = yield
            called.append('post1')

        def extension2(req):
            called.append('pre2')
            resp_obj = yield
            called.append('post2')

        extensions = [extension1, extension2]
        response, post = resource.pre_process_extensions(extensions, None, {})
        post = list(post)
        self.assertEqual(called, ['pre1', 'pre2'])
        self.assertEqual(response, None)
        self.assertEqual(len(post), 2)
        self.assertTrue(inspect.isgenerator(post[0]))
        self.assertTrue(inspect.isgenerator(post[1]))

        for gen in post:
            try:
                gen.send(None)
            except StopIteration:
                continue

        self.assertEqual(called, ['pre1', 'pre2', 'post2', 'post1'])

    def test_pre_process_extensions_generator_response(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)

        called = []

        def extension1(req):
            called.append('pre1')
            yield 'foo'

        def extension2(req):
            called.append('pre2')

        extensions = [extension1, extension2]
        response, post = resource.pre_process_extensions(extensions, None, {})
        self.assertEqual(called, ['pre1'])
        self.assertEqual(response, 'foo')
        self.assertEqual(post, [])

    def test_post_process_extensions_regular(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)

        called = []

        def extension1(req, resp_obj):
            called.append(1)
            return None

        def extension2(req, resp_obj):
            called.append(2)
            return None

        response = resource.post_process_extensions([extension2, extension1],
                                                    None, None, {})
        self.assertEqual(called, [2, 1])
        self.assertEqual(response, None)

    def test_post_process_extensions_regular_response(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)

        called = []

        def extension1(req, resp_obj):
            called.append(1)
            return None

        def extension2(req, resp_obj):
            called.append(2)
            return 'foo'

        response = resource.post_process_extensions([extension2, extension1],
                                                    None, None, {})
        self.assertEqual(called, [2])
        self.assertEqual(response, 'foo')

    def test_post_process_extensions_generator(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)

        called = []

        def extension1(req):
            resp_obj = yield
            called.append(1)

        def extension2(req):
            resp_obj = yield
            called.append(2)

        ext1 = extension1(None)
        next(ext1)
        ext2 = extension2(None)
        next(ext2)

        response = resource.post_process_extensions([ext2, ext1],
                                                    None, None, {})

        self.assertEqual(called, [2, 1])
        self.assertEqual(response, None)

    def test_post_process_extensions_generator_response(self):
        class Controller(object):
            def index(self, req, pants=None):
                return pants

        controller = Controller()
        resource = wsgi.Resource(controller)

        called = []

        def extension1(req):
            resp_obj = yield
            called.append(1)

        def extension2(req):
            resp_obj = yield
            called.append(2)
            yield 'foo'

        ext1 = extension1(None)
        next(ext1)
        ext2 = extension2(None)
        next(ext2)

        response = resource.post_process_extensions([ext2, ext1],
                                                    None, None, {})

        self.assertEqual(called, [2])
        self.assertEqual(response, 'foo')


class ResponseObjectTest(test.TestCase):
    def test_default_code(self):
        robj = wsgi.ResponseObject({})
        self.assertEqual(robj.code, 200)

    def test_modified_code(self):
        robj = wsgi.ResponseObject({})
        robj._default_code = 202
        self.assertEqual(robj.code, 202)

    def test_override_default_code(self):
        robj = wsgi.ResponseObject({}, code=404)
        self.assertEqual(robj.code, 404)

    def test_override_modified_code(self):
        robj = wsgi.ResponseObject({}, code=404)
        robj._default_code = 202
        self.assertEqual(robj.code, 404)

    def test_set_header(self):
        robj = wsgi.ResponseObject({})
        robj['Header'] = 'foo'
        self.assertEqual(robj.headers, {'header': 'foo'})

    def test_get_header(self):
        robj = wsgi.ResponseObject({})
        robj['Header'] = 'foo'
        self.assertEqual(robj['hEADER'], 'foo')

    def test_del_header(self):
        robj = wsgi.ResponseObject({})
        robj['Header'] = 'foo'
        del robj['hEADER']
        self.assertFalse('header' in robj.headers)

    def test_header_isolation(self):
        robj = wsgi.ResponseObject({})
        robj['Header'] = 'foo'
        hdrs = robj.headers
        hdrs['hEADER'] = 'bar'
        self.assertEqual(robj['hEADER'], 'foo')

    def test_default_serializers(self):
        robj = wsgi.ResponseObject({})
        self.assertEqual(robj.serializers, {})

    def test_bind_serializers(self):
        robj = wsgi.ResponseObject({}, json='foo')
        robj._bind_method_serializers(dict(xml='bar', json='baz'))
        self.assertEqual(robj.serializers, dict(xml='bar', json='foo'))

    def test_get_serializer(self):
        robj = wsgi.ResponseObject({}, json='json', xml='xml', atom='atom')
        for content_type, mtype in wsgi._MEDIA_TYPE_MAP.items():
            _mtype, serializer = robj.get_serializer(content_type)
            self.assertEqual(serializer, mtype)

    def test_get_serializer_defaults(self):
        robj = wsgi.ResponseObject({})
        default_serializers = dict(json='json', xml='xml', atom='atom')
        for content_type, mtype in wsgi._MEDIA_TYPE_MAP.items():
            self.assertRaises(exception.InvalidContentType,
                              robj.get_serializer, content_type)
            _mtype, serializer = robj.get_serializer(content_type,
                                                     default_serializers)
            self.assertEqual(serializer, mtype)

    def test_serialize(self):
        class JSONSerializer(object):
            def serialize(self, obj):
                return 'json'

        class XMLSerializer(object):
            def serialize(self, obj):
                return 'xml'

        class AtomSerializer(object):
            def serialize(self, obj):
                return 'atom'

        robj = wsgi.ResponseObject({}, code=202,
                                   json=JSONSerializer,
                                   xml=XMLSerializer,
                                   atom=AtomSerializer)
        robj['X-header1'] = 'header1'
        robj['X-header2'] = 'header2'

        for content_type, mtype in wsgi._MEDIA_TYPE_MAP.items():
            request = wsgi.Request.blank('/tests/123')
            response = robj.serialize(request, content_type)

            self.assertEqual(response.headers['Content-Type'], content_type)
            self.assertEqual(response.headers['X-header1'], 'header1')
            self.assertEqual(response.headers['X-header2'], 'header2')
            self.assertEqual(response.status_int, 202)
            self.assertEqual(response.body, mtype)


class ValidBodyTest(test.TestCase):

    def setUp(self):
        super(ValidBodyTest, self).setUp()
        self.controller = wsgi.Controller()

    def test_is_valid_body(self):
        body = {'foo': {}}
        self.assertTrue(self.controller.is_valid_body(body, 'foo'))

    def test_is_valid_body_none(self):
        resource = wsgi.Resource(controller=None)
        self.assertFalse(self.controller.is_valid_body(None, 'foo'))

    def test_is_valid_body_empty(self):
        resource = wsgi.Resource(controller=None)
        self.assertFalse(self.controller.is_valid_body({}, 'foo'))

    def test_is_valid_body_no_entity(self):
        resource = wsgi.Resource(controller=None)
        body = {'bar': {}}
        self.assertFalse(self.controller.is_valid_body(body, 'foo'))

    def test_is_valid_body_malformed_entity(self):
        resource = wsgi.Resource(controller=None)
        body = {'foo': 'bar'}
        self.assertFalse(self.controller.is_valid_body(body, 'foo'))
