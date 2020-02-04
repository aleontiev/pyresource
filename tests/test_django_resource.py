from django_resource import __version__
from django_resource.space import Space
from django_resource.resource import Resource
from django_resource.server import Server
from django_resource.test import TestAPIClient


def test_version():
    assert __version__ == '0.1.0'


def test_integration():
    server = Server(url='http://test.localhost')
    test = Space(name='test', server=server)
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
                    'edit': False,
                    'add': False
                }
            },
        },
        can=['get', 'inspect', 'add', 'set', 'edit', 'delete'],
    )
    # client
    # users.id == 'test.users'
    # users.name == 'users'
    # users.space == (Space: test)
    client = TestAPIClient()
    # get.resource
    client.get(
        '/api/test/users/'
    )
    # get.record

    #

    # users.data.get()
    # -> GET /users/
    # ->
    # {
    #   "key": {"users": ["1", "2", "3"]},
    #   "data": {
    #       "users": {
    #           "1": {
    #           }
    #       }
    #   },
    #   "meta": {
    #     "page": {
    #       "next": "abcdefg1234==",
    #       "more": {
    #           "users": true
    #       }
    #     }
    #   }
    # }
    #

    # users.data.with('email').get(1)
    # -> GET /users/1/?with=email
    # -> 
    # {
    #   "key": {"users": "1"},
    #   "data": {
    #       "users": {
    #           "1": {
    #               "email": "foobar",
    #           }
    #       }
    #   }
    # }

    # users.data.get(1, 'email')
    # -> GET /users/1/email/
    # ->
    # {
    #   "key": 
    # }

    # users.data
    #  .with('-latestGroup')
    #  .where('name', 'icontains', 'B')
    #  .with.groups('*')
    #  .group('created', 'max', 'latest_created')
    #  .where.groups('name', 'icontains', 'test')
    #  .with.groups.location('*')

    #  .get()

    # users.data.from

    # ~ GET /users/?if:latestGroup.name=123&if:name=A&if:latestGroup.name:contains=test&if=(1|2)&!3
    #           &with=-latestGroup&with=groups.*
    #           &if:name:icontains=test

    #  .if('groups.a', 'name', 'icontains', 'test')
    #  .if('groups.b', 'name', 'icontains', 'abc')
    #  .if('groups.', 'a | b')
