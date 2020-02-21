from django.test import TestCase
from django_resource import __version__
from django_resource.space import Space
from django_resource.resource import Resource
from django_resource.server import Server




class IntegrationTestCase(django.T
    def test_version(self):
        self.assertEqual(__version__, '0.1.0')

    def test_social_network(self):
        # social network integration setup
        # one space: test
        # three collections:
        # - users (auth.user)
        # - groups (auth.group)
        # - posts (custom model with a creator and a group)
        # one singletons: session (for authentication)

        # 1. login
        # Request:
        #     POST /api/test/session?take.user=name,email {"username": "test", "password": "test"}
        # Success:
        #     201 {"data": {"users": {"1234": {"name": "Joe Smith", "email": "joe@smith.com"}}, "session": {"user": "1234"}}}
        # Failure:
        #     403 {"errors": {"response": {"session": {"password": "invalid password provided"}}}}
        #     400 {"errors": {"request": {"take.user": {"name": "invalid field"}}}}

        # 2a. view profile
        # Request:
        #     GET /api/test/session/user/?take=name
        # Success:
        #     200 {"data": {"session": {"user": "1234"}, {"users": {"1234": {"name": "John"}}}}}

        # 2b. change name
        # Request:
        #     PATCH /api/test/users/1234 {"name": "Jim"}
        # Success:
        #     200 {"data": {"users": {"1234": {"name": "Jim", "updated": "2020-01-01T00:00:00Z"}}}}

        # 2c. change password
        # Request:
        #     POST /api/test/users/1234?method=change-password {"old_password": "123", "new_password": "asd", "confirm_password": "asd"}
        # Success:
        #     200 {"key": ["users", "1234"], "data": {"users": {"1234": {"updated": "2020-01-01T00:00:00Z"}}}}
        # Failure:
        #     400 {
        #       "errors": {
        #           "body": {
        #               "old_password": ["this field is required"],
        #               "confirm_password": ["does not match new password"],
        #               "new_password": ["must have at least one symbol"]
        #           }
        #        }
        #     }
        #     400 {
        #       "errors": {
        #           "data": {
        #               "session": {
        #                   "old_password": [
        #                       "incorrect password"
        #                   ]
        #               }
        #           }
        #        }
        #     }

        # 3. list users, groups, and users in groups
        # Request:
        #     GET /api/test/?take.users=name&take.groups=name&take.groups.users=name
        # Success:
        #     200 {
        #         "key": ["."],
        #         "data": {
        #             ".": {"users": [1, 2, 3, 4], "groups": [1, 2, 3, 4]}},
        #             "users": {...},
        #             "groups": {...},
        #         }
        #     }

        server = Server(
            url='http://localhost/api',
        )
        test = Space(name='test', server=server)

        def login(resource, request, query):
            api_key = query.state['.body').get('api_key')
            api_key = json.loads(str(base64.b64decode(api_key)))
            if authenticate(username, password):
                pass

        def logout(resource, request, query):
            pass

        def change_password(resource):
            pass

        session = Resource(
            id='test.session',
            name='session',
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
                    "type": "?@users",
                    "source": ".request.user.id"
                },
                "username": {
                    "type": "string",
                    "can": {"login": True, "get": False, "set": False}
                },
                "password": {
                    "type": "string",
                    "can": {"login": True, "get": False, "set": False}
                }
            },
            methods={
                'login': login,
                'logout': logout
            }
        )

        users = Resource(
            id='test.users',
            name='users',
            source='auth.user',
            space=test,
            fields={
                'id': 'id',
                'name': 'last_name',
                'email': 'email',
                'groups': {
                    'inverse': 'users',
                    'lazy': True,
                    'default': [],
                    'can': {
                        'set': False,
                        'delete': False
                    }
                },
            },
            can={
                'get': {
                    '.or': [{
                        'id': {
                            '.equals': '.request.user.id'
                        }
                    }, {
                        '.request.user.id': {
                            '.in': 'groups.users'
                        }
                    }, {
                        '.request.user.is_superuser': True
                    }]
                },
                'inspect': True,
                'add': {'.request.user.is_superuser': True},
                'set': {'.request.user.is_superuser': True},
                'edit': {'.request.user.is_superuser': True},
                'delete': {'.request.user.is_superuser': True},
                'change-password': {'id': {'.equals': '.request.user.id'}}
            },
            parameters={
                'change-password': {
                    'old_password': {
                        'type': 'string',
                    },
                    'new_password': {
                        'type': {
                            'is': 'string',
                            'min_length': 10,
                        },
                    },
                    'confirm_password': {
                        'type': 'string',
                    }
                }
            },
            before={
                'change-password': {
                    'check': {
                        '.equal': [
                            'confirm_password',
                            'new_password'
                        ]
                    }
                }
            },
            methods={
                'change-password': change_password,
            }
        )
        self.assertEqual(users.id, 'test.users')
        self.assertEqual(users.space.name, 'test')
        self.assertEqual(users.space, test)

        query1 = test.query('users?take=id,name&page.size=10&method=get')
        test.query('?take.users=id,name&page.size=10&take.groups=id')
        # ~ /users/?show=id + /groups/?show=id
        # -> {"data": {"users": ...}}
        query = test.users.query(f'/{user.id}/?show=id,name&page.size=2&method=get')
        query2 = (
            test.query
            .resource('users')
            .show('id', 'name')
            .page(size=10).
            .method('get')
        )
        self.assertEqual(query.state, query2.state)

        context = {
            'request': {
                'user': {
                    'id': '1', 'is_superuser': True
                }
            }
        }
        result = query.execute(**context)

        main = result.main
        data = result.data
        meta = result.meta

