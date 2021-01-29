import base64
import json
from django.test import TestCase
from django_resource import __version__
from django_resource.space import Space
from django_resource.resource import Resource
from django_resource.server import Server
from tests.models import User, Group, Location
from .utils import Request, Fixture

# basic features:
# - actions: get, set, add, edit, delete, explain
# - endpoints: server, space, resource, record, field
# - features: sort, filter, group, page

# advanced features:
# - inspecting metadata
# - deep filtering & sorting
# - computed fields
# - before & after hooks
# - authorization
# - custom actions

def get_fixture():
    userA = User.make(family_name='A', first_name='Alex')
    userB = User.make(family_name='B', first_name='Bay')
    userC = User.make(is_active=False, first_name='Inactive', family_name='I')
    groupA = Group.make(name='A')
    groupB = Group.make(name='B')
    groupC = Group.make(name='C')
    userA.groups.set([groupA, groupB])
    userB.groups.set([groupA])
    return Fixture(
        users=[userA, userB, userC],
        groups=[groupA, groupB, groupC]
    )


server = None
def get_server():
    global server
    if server is not None:
        # cache the server spec since it doesn't change
        # across test cases
        return server

    # social network integration setup
    # one space: test
    # three collections:
    # - users 
    # - groups 
    # - location 
    # one singleton:
    # - session (for authentication)
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
            'get': True
        },
        fields={
            "user": {
                "type": ["null", "@users"],
                "source": ".request.user"
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
        source={
            'queryset': {
                'model': 'tests.group',
                'where': {
                    'true': 'is_active'
                }
            }
        },
        space=tests,
        fields={
            'id': 'id',
            'name': 'name',
            'users': {
                'source': {
                    'queryset': {
                        'field': 'users',
                        'sort': 'created'
                    }
                },
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
            'last_name': 'family_name',  # renamed field
            'name': {
                'type': 'string',
                'source': {
                    'concat': [
                        'first_name',
                        '" "',
                        'family_name'
                    ],
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
                    # can only set if the new value is smaller {'>': ['.changes.groups', 'groups']}
                    # can only set if name is not changing {'null': '.changes.name'}
                    'add': True,
                    'get': True,
                },
                'source': {
                    'queryset': {
                        'field': 'groups',
                        'sort': 'name',
                        'where': {
                            'true': 'is_active'
                        }
                    }
                }
            },
            'created': {
                'lazy': True,
                'default': {
                    'now': {}
                },
                'can': {'get': True}
            },
            'updated': {
                'lazy': True,
                'default': {
                    'now': {}
                },
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
    return server


class IntegrationTestCase(TestCase):
    maxDiff = None

    def test_version(self):
        self.assertEqual(__version__, '0.1.0')

    def test_setup_server(self):
        server = get_server()
        tests = server.spaces_by_name['tests']
        users = tests.resources_by_name['users']
        groups = tests.resources_by_name['groups']
        session = tests.resources_by_name['session']

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

    def test_get_space(self):
        server = get_server()
        tests = server.spaces_by_name['tests']

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        groupA, groupB, groupC = fixture.groups
        request = Request(userA)

        self.assertEqual(
            tests.query.get(request=request), {
                'data': {
                    'users': './users/',
                    'groups': './groups/',
                    'session': './session/'
                }
            }
        )

        get_all = (
            tests.query
            .take.users('id')
            .take.groups('id')
            .take.session('*')
            .get(request=request)
        )
        self.assertEqual(
            get_all, {
                'data': {
                    'users': [{
                        'id': str(userA.id),
                    }, {
                        'id': str(userB.id)
                    }],
                    'groups': [{
                        'id': str(groupA.id)
                    }, {
                        'id': str(groupB.id)
                    }, {
                        'id': str(groupC.id)
                    }],
                    'session': {
                        'user': str(userA.id)
                    }
                }
            }
        )

        get_with_filters = (
            tests.query
            .take.users('id')
            .take.users.groups('id')
            .where.users({'=': ['id', f'"{userA.id}"']})
            .take.groups('id')
            .where.groups({'=': ['id', f'"{groupA.id}"']})
            .get(request=request)
        )
        self.assertEqual(
            get_with_filters, {
                'data': {
                    'users': [{
                        'id': str(userA.id),
                        'groups': [{
                            'id': str(groupA.id)
                        }, {
                            'id': str(groupB.id)
                        }]
                    }],
                    'groups': [{
                        'id': str(groupA.id)
                    }],
                }
            }
        )

    def test_get_server(self):
        server = get_server()

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        groupA, groupB, groupC = fixture.groups
        request = Request(userA)

        self.assertEqual(
            server.query.get(request=request), {
                'data': {
                    'tests': './tests/',
                }
            }
        )

        get_all = (
            server.query
            .take.tests.users('id')
            .take.tests.groups('id')
            .take.tests.session('*')
            .get(request=request)
        )
        self.assertEqual(
            get_all, {
                'data': {
                    'tests': {
                        'users': [{
                            'id': str(userA.id),
                        }, {
                            'id': str(userB.id)
                        }],
                        'groups': [{
                            'id': str(groupA.id)
                        }, {
                            'id': str(groupB.id)
                        }, {
                            'id': str(groupC.id)
                        }],
                        'session': {
                            'user': str(userA.id)
                        }
                    }
                }
            }
        )

        get_with_filters = (
            server.query
            .take.tests.users('id')
            .take.tests.users.groups('id')
            .where.tests.users({'=': ['id', f'"{userA.id}"']})
            .take.tests.groups('id')
            .where.tests.groups({'=': ['id', f'"{groupA.id}"']})
            .get(request=request)
        )
        self.assertEqual(
            get_with_filters, {
                'data': {
                    'tests': {
                        'users': [{
                            'id': str(userA.id),
                            'groups': [{
                                'id': str(groupA.id)
                            }, {
                                'id': str(groupB.id)
                            }]
                        }],
                        'groups': [{
                            'id': str(groupA.id)
                        }]
                    }
                }
            }
        )

    def test_get_resource(self):
        """Tests get_resource"""
        server = get_server()
        tests = server.spaces_by_name['tests']
        users = tests.resources_by_name['users']
        groups = tests.resources_by_name['groups']
        session = tests.resources_by_name['session']

        self.assertEqual(users.query.get(), {'data': []})

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        groupA, groupB, groupC = fixture.groups

        ## selecting
        session_get = session.query.get(
            request=Request(userA)
        )
        self.assertEqual(session_get, {
            'data': {
                'user': str(userA.id)
            }
        })
        session_take_user = session.query.take.user('id', 'first_name').get(
            request=Request(userA)
        )
        self.assertEqual(session_take_user, {
            'data': {
                'user': {
                    'id': str(userA.id),
                    'first_name': userA.first_name
                }
            }
        })

        simple_get = users.query.get()
        self.assertEqual(
            simple_get,
            {
                'data': [{
                    'id': str(userA.id),
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.family_name,
                    'name': f'{userA.first_name} {userA.family_name}',
                }, {
                    'id': str(userB.id),
                    'email': userB.email,
                    'first_name': userB.first_name,
                    'last_name': userB.family_name,
                    'name': f'{userB.first_name} {userB.family_name}'
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

        dont_take_id = users.query.take('*', '-id', '-name').get()
        self.assertEqual(
            dont_take_id,
            {
                'data': [{
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.family_name,
                }, {
                    'email': userB.email,
                    'first_name': userB.first_name,
                    'last_name': userB.family_name,
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

        take_groups = users.query.take('*', 'groups', '-name').get()
        self.assertEqual(
            take_groups,
            {
                'data': [{
                    'id': str(userA.id),
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.family_name,
                    'groups': [str(groupA.id), str(groupB.id)]
                }, {
                    'id': str(userB.id),
                    'email': userB.email,
                    'first_name': userB.first_name,
                    'last_name': userB.family_name,
                    'groups': [str(groupA.id)]
                }]
            }
        )

        prefetch_groups = users.query('?take=*,-name&take.groups=*').get()
        self.assertEqual(
            prefetch_groups,
            {
                'data': [{
                    'id': str(userA.id),
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.family_name,
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
                    'last_name': userB.family_name,
                    'groups': [{
                        'id': str(groupA.id),
                        'name': groupA.name
                    }]
                }]
            }
        )

        prefetch_deep_query = users.query('?take=*,-name&take.groups=*&take.groups.users=id')
        prefetch_deep = prefetch_deep_query.get()
        self.assertEqual(
            prefetch_deep,
            {
                'data': [{
                    'id': str(userA.id),
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.family_name,
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
                    'last_name': userB.family_name,
                    'groups': [{
                        'id': str(groupA.id),
                        'name': groupA.name,
                        'users': [{'id': str(userA.id)}, {'id': str(userB.id)}],
                    }]
                }]
            }
        )

        ## filtering

        get_where = (
            users.query
            .take('id')
            .where({
                'contains': ['first_name', f'"{userA.first_name}"']
            })
            .get()
        )
        self.assertEqual(
            get_where,
            {
                'data': [{
                    'id': str(userA.id)
                }]
            }
        )

        get_where_related = (
            users.query
            .take('id')
            .where({
                'null': 'groups'
            })
            .get()
        )
        self.assertEqual(
            get_where_related,
            {
                'data': []
            }
        )

        ## sorting

        sort_descending = users.query.take('id').sort('-last_name').get()
        self.assertEqual(
            sort_descending,
            {
                'data': [{
                    'id': str(userB.id)
                }, {
                    'id': str(userA.id)
                }]
            }
        )

        sort_ascending = users.query.take('id').sort('last_name').get()
        self.assertEqual(
            sort_descending,
            {
                'data': [{
                    'id': str(userB.id)
                }, {
                    'id': str(userA.id)
                }]
            }
        )

        ## paginating

        page_1 = users.query.take('id').page(size=1).get()
        after = base64.b64encode(json.dumps({'offset': 1}).encode('utf-8'))
        self.assertEqual(
            page_1,
            {
                'data': [{
                    'id': str(userA.id)
                }],
                'meta': {
                    'page': {
                        'data': {
                            'after': after,
                            'total': 2
                        }
                    }
                }
            }
        )
        page_2 = users.query.take('id').page(size=1, after=after).get()
        self.assertEqual(
            page_2,
            {
                'data': [{
                    'id': str(userB.id)
                }]
            }
        )

    def test_get_record(self):
        """Tests get_record"""
        server = get_server()
        tests = server.spaces_by_name['tests']
        users = tests.resources_by_name['users']
        groups = tests.resources_by_name['groups']

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        groupA, groupB, groupC = fixture.groups

        ## selecting
        simple_get = users.query.get(userA.id)
        self.assertEqual(
            simple_get,
            {
                'data': {
                    'id': str(userA.id),
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.family_name,
                    'name': f'{userA.first_name} {userA.family_name}'
                }
            }
        )

        take_id_only = users.query.take('id').get(userA.id)
        self.assertEqual(
            take_id_only,
            {
                'data': {
                    'id': str(userA.id)
                }
            }
        )

        dont_take_id = users.query.take('*', '-id').get(userA.id)
        self.assertEqual(
            dont_take_id,
            {
                'data': {
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.family_name,
                    'name': f'{userA.first_name} {userA.family_name}'
                }
            }
        )

        take_nothing = users.query.take('-id').get(userA.id)
        self.assertEqual(
            take_nothing,
            {
                'data': {}
            }
        )

        take_groups = users.query.take('*', 'groups').get(userA.id)
        self.assertEqual(
            take_groups,
            {
                'data': {
                    'id': str(userA.id),
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.family_name,
                    'name': f'{userA.first_name} {userA.family_name}',
                    'groups': [str(groupA.id), str(groupB.id)]
                }
            }
        )

        prefetch_groups = users.query('?take=*&take.groups=*').get(userA.id)
        self.assertEqual(
            prefetch_groups,
            {
                'data': {
                    'id': str(userA.id),
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.family_name,
                    'name': f'{userA.first_name} {userA.family_name}',
                    'groups': [{
                        'id': str(groupA.id),
                        'name': groupA.name
                    }, {
                        'id': str(groupB.id),
                        'name': groupB.name
                    }]
                }
            }
        )

        prefetch_deep_query = users.query('?take=*&take.groups=*&take.groups.users=id')
        prefetch_deep = prefetch_deep_query.get(userA.id)
        self.assertEqual(
            prefetch_deep,
            {
                'data': {
                    'id': str(userA.id),
                    'email': userA.email,
                    'first_name': userA.first_name,
                    'last_name': userA.family_name,
                    'name': f'{userA.first_name} {userA.family_name}',
                    'groups': [{
                        'id': str(groupA.id),
                        'name': groupA.name,
                        'users': [{'id': str(userA.id)}, {'id': str(userB.id)}],
                    }, {
                        'id': str(groupB.id),
                        'name': groupB.name,
                        'users': [{'id': str(userA.id)}]
                    }]
                }
            }
        )

    def test_get_field(self):
        """Tests get_field"""
        server = get_server()
        tests = server.spaces_by_name['tests']
        users = tests.resources_by_name['users']
        groups = tests.resources_by_name['groups']

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        groupA, groupB, groupC = fixture.groups

        ## selecting
        simple_get = users.query.get(userA.id, 'first_name')
        self.assertEqual(
            simple_get,
            {
                'data': userA.first_name
            }
        )

        take_groups = users.query.get(userA.id, 'groups')
        self.assertEqual(
            take_groups,
            {
                'data': [str(groupA.id), str(groupB.id)]
            }
        )

        prefetch_groups = users.query('?take=id,name').get(userA.id, 'groups')
        self.assertEqual(
            prefetch_groups,
            {
                'data': [{
                    'id': str(groupA.id),
                    'name': groupA.name
                }, {
                    'id': str(groupB.id),
                    'name': groupB.name
                }]
            }
        )

        prefetch_deep = users.query(
            '?take=id,name,users&take.users=id'
        ).get(userA.id, 'groups')
        self.assertEqual(
            prefetch_deep,
            {
                'data': [{
                    'id': str(groupA.id),
                    'name': groupA.name,
                    'users': [{
                        'id': str(userA.id),
                    }, {
                        'id': str(userB.id)
                    }]
                }, {
                    'id': str(groupB.id),
                    'name': groupB.name,
                    'users': [{
                        'id': str(userA.id)
                    }]
                }]
            }
        )
