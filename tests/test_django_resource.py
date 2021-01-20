from django.test import TestCase
from django_resource import __version__
from django_resource.space import Space
from django_resource.resource import Resource
from django_resource.server import Server
from tests.models import User, Group, Location



def get_fixture():
    server = Server(
        url='http://localhost/api/',
    )

    tests = Space(name='tests', server=server)

    def login(resource, request, query):
        api_key = query.state('body').get('api_key')
        api_key = json.loads(str(base64.b64decode(api_key)))
        if authenticate(username, password):
            pass

    def logout(resource, request, query):
        pass

    def change_password(resource, request, query):
        pass

    session = Resource(
        id='tests.session',
        name='session',
        space=tests,
        singleton=True,
        can={
            'login': True,
            'logout': True,
            'add': False,
            'set': False,
            'edit': False,
            'delete': False
        },
        fields={
            "user": {
                "type": ["null", "@users"],
                "source": ".request.user.id"
            },
        },
        actions={
            'login': {
                'method': login,
                'fields': {
                    "username": {
                        "type": "string",
                        "can": {'set': True}
                    },
                    "password": {
                        "type": "string",
                        "can": {'set': True}
                    },
                    "status": {
                        "type": "string",
                        "can": {'get': True}
                    }
                }
            },
            'logout': logout
        }
    )
    groups = Resource(
        id='tests.groups',
        name='groups',
        source='tests.group',
        space=tests,
        fields={
            'id': 'id',
            'name': 'name',
            'users': {
                'lazy': True,
                'can': {'get': True},
            },
            'created': {
                'lazy': True,
                'can': {'get': True}
            },
            'updated': {
                'lazy': True,
                'can': {'get': True}
            }
        },
        can={
            '*': {'true': '.request.user.is_superuser'},
            'get': {'=': ['users', '.request.user.id']},
        }
    )

    users = Resource(
        id='tests.users',
        name='users',
        source={
            'queryset': {
                'model': 'tests.user',
                'where': {
                    'true': 'is_active'
                },
                'sort': 'created'
            }
        },
        space=tests,
        fields={
            'id': 'id',
            'first_name': 'first_name',
            'last_name': 'last_name',
            'name': {
                'type': 'string',
                'source': {
                    'concat': [
                        'first_name',
                        '" "',
                        'last_name'
                    ]
                },
                'can': {
                    'get': True,
                }
            },
            'email': 'email',
            'groups': {
                'lazy': True,
                'can': {
                    'set': {'=': ['.query.action', '"add"']},
                    'add': True,
                    'get': True,
                },
                'source': {
                    'queryset': {
                        'field': 'groups',
                        'sort': 'created'
                    }
                }
            },
            'created': {
                'lazy': True,
                'can': {'get': True}
            },
            'updated': {
                'lazy': True,
                'can': {'get': True}
            }
        },
        can={
            '*': {'true': '.request.user.is_superuser'},
            'get, change-password': {'=': ['id', '.request.user.id']}
        },
        before={
            'change-password': {
                'check': {
                    '=': [
                        'confirm_password',
                        'new_password'
                    ]
                }
            }
        },
        actions={
            'change-password': {
                'method': change_password,
                'fields': {
                    'old_password': {
                        'type': 'string',
                        'can': {'set': True}
                    },
                    'new_password': {
                        'type': {
                            'type': 'string',
                            'min_length': 10,
                        },
                        'can': {'set': True}
                    },
                    'confirm_password': {
                        'type': 'string',
                        'can': {'set': True}
                    },
                    'changed': {
                        'type': 'boolean',
                        'can': {'get': True}
                    }
                }
            }
        }
    )
    return {
        'server': server,
        'tests': tests,
        'users': users,
        'groups': groups,
        'session': session
    }


class IntegrationTestCase(TestCase):
    maxDiff = None

    def test_version(self):
        self.assertEqual(__version__, '0.1.0')

    def test_mvp(self):
        # social network integration setup
        # one space: test
        # three collections:
        # - users 
        # - groups 
        # - location 
        # one singleton:
        # - session (for authentication)
        fixture = get_fixture()
        users = fixture['users']
        groups = fixture['groups']
        tests = fixture['tests']
        server = fixture['server']

        self.assertEqual(groups.id, 'tests.groups')
        self.assertEqual(users.id, 'tests.users')
        self.assertEqual(users.space.name, 'tests')
        self.assertEqual(users.space, tests)
        self.assertEqual(server.url, 'http://localhost/api/')
        self.assertEqual(tests.url, 'http://localhost/api/tests/')
        self.assertEqual(users.url, 'http://localhost/api/tests/users/')

        query1 = tests.query(
            'users'
            '?take=id,name'
            '&page:size=10'
            '&action=get'
        )
        query2 = (
            tests.query
            .resource('users')
            .take('id', 'name')
            .page(size=10)
            .action('get')
        )
        self.assertEqual(query1.state, query2.state)

        query3 = tests.query(
            '?take.users=*,-name'
            '&take.groups=id'
            '&page.users:size=5'
            '&page.users:after=ABC'
            '&sort.groups=-created,id'
            '&where.groups:updated:gte=created'
            '&where.users:name:contains="Joe"'
        )
        query4 = (
            tests.query
            .take.users('*', '-name')
            .page.users(after='ABC', size=5)
            .take.groups('id')
            .sort.groups('-created', 'id')
            .where.groups({'gte': ['updated', 'created']})
            .where.users({'contains': ['name', '"Joe"']})
        )
        self.assertEqual(query3.state, query4.state)
        self.assertEqual(query3.state, {
            'take': {
                'groups': {
                    'sort': ['-created', 'id'],
                    'take': {
                        'id': True
                    },
                    'where': {
                        'gte': ['updated', 'created']
                    }
                },
                'users': {
                    'page': {
                        'after': 'ABC',
                        'size': 5
                    },
                    'take': {
                        '*': True,
                        'name': False
                    },
                    'where': {
                        'contains': ['name', '"Joe"']
                    }
                }
            },
            'space': 'tests'
        })

        query5 = tests.query(
            '/users/1/groups'
            '?take=id,name'
        )
        query6 = (
            tests.query
            .resource('users')
            .record('1')
            .field('groups')
            .take('id', 'name')
        )
        self.assertEqual(query5.state, query6.state)
        id = users.get_field('id')
        self.assertEqual(id.resource, users)

        # empty request before any data exists
        self.assertEqual(users.query.get(), {'data': []})

        # setup data
        userA = User.make(last_name='A', first_name='Alex')
        userB = User.make(last_name='B', first_name='Bay')
        userC = User.make(is_active=False, first_name='Inactive', last_name='I')
        groupA = Group.make(name='A')
        groupB = Group.make(name='B')
        groupC = Group.make(name='C')
        userA.groups.set([groupA, groupB])
        userB.groups.set([groupA])

        simple_get = users.query.get()
        self.assertEqual(
            simple_get,
            {
                'data': [{
                    'id': str(userA.id),
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.last_name,
                    'name': None  # TODO: fix this
                }, {
                    'id': str(userB.id),
                    'email': userB.email,
                    'first_name': userB.first_name,
                    'last_name': userB.last_name,
                    'name': None  # TODO: fix this
                }]
            }
        )

        take_id_only = users.query.take('id').get()
        self.assertEqual(
            take_id_only,
            {
                'data': [{
                    'id': str(userA.id)
                }, {
                    'id': str(userB.id)
                }]
            }
        )

        dont_take_id = users.query.take('*', '-id').get()
        self.assertEqual(
            dont_take_id,
            {
                'data': [{
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.last_name,
                    'name': None
                }, {
                    'email': userB.email,
                    'first_name': userB.first_name,
                    'last_name': userB.last_name,
                    'name': None
                }]
            }
        )
        take_nothing = users.query.take('-id').get()
        self.assertEqual(
            take_nothing,
            {
                'data': [{}, {}]
            }
        )

        take_groups = users.query.take('*', 'groups').get()
        self.assertEqual(
            take_groups,
            {
                'data': [{
                    'id': str(userA.id),
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.last_name,
                    'name': None,
                    'groups': [str(groupA.id), str(groupB.id)]
                }, {
                    'id': str(userB.id),
                    'email': userB.email,
                    'first_name': userB.first_name,
                    'last_name': userB.last_name,
                    'name': None,
                    'groups': [str(groupA.id)]
                }]
            }
        )

        prefetch_groups = users.query('?take=*&take.groups=*').get()
        self.assertEqual(
            prefetch_groups,
            {
                'data': [{
                    'id': str(userA.id),
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.last_name,
                    'name': None,
                    'groups': [{
                        'id': str(groupA.id),
                        'name': groupA.name
                    }, {
                        'id': str(groupB.id),
                        'name': groupB.name
                    }]
                }, {
                    'id': str(userB.id),
                    'email': userB.email,
                    'first_name': userB.first_name,
                    'last_name': userB.last_name,
                    'name': None,
                    'groups': [{
                        'id': str(groupA.id),
                        'name': groupA.name
                    }]
                }]
            }
        )

        # prefetch_deep
        prefetch_deep_query = users.query('?take=*&take.groups=*&take.groups.users=id')
        prefetch_deep = prefetch_deep_query.get()
        self.assertEqual(
            prefetch_deep,
            {
                'data': [{
                    'id': str(userA.id),
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.last_name,
                    'name': None,
                    'groups': [{
                        'id': str(groupA.id),
                        'name': groupA.name,
                        'users': [{'id': str(userA.id)}, {'id': str(userB.id)}],
                    }, {
                        'id': str(groupB.id),
                        'name': groupB.name,
                        'users': [{'id': str(userA.id)}]
                    }]
                }, {
                    'id': str(userB.id),
                    'email': userB.email,
                    'first_name': userB.first_name,
                    'last_name': userB.last_name,
                    'name': None,
                    'groups': [{
                        'id': str(groupA.id),
                        'name': groupA.name,
                        'users': [{'id': str(userA.id)}, {'id': str(userB.id)}],
                    }]
                }]
            }
        )

        # ordered
        # filtered
        # paginated
        # add
        # set
        # edit
        # delete
        # custom methods
