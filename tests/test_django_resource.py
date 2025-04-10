"""Tests on Django engine"""
import base64
import json
from urllib.parse import quote
from django.test import TestCase
from pyresource import __version__
from pyresource.space import Space
from pyresource.resource import Resource
from pyresource.server import Server
from pyresource.utils.types import types
from pyresource.schemas import (
    SpaceSchema,
    ResourceSchema,
    FieldSchema,
    ServerSchema,
    TypeSchema
)
from pyresource.conf import settings
from tests.models import User, Group, Location
from .server import get_server
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
    userA = User.make(family_name="A", first_name="Alex", is_superuser=True, is_staff=True)
    userA.set_password(userA.email)
    userA.save()
    userB = User.make(family_name="B", first_name="Bay")
    userC = User.make(is_active=False, first_name="Inactive", family_name="I")
    groupA = Group.make(name="A")
    groupB = Group.make(name="B")
    groupC = Group.make(name="C")
    userA.groups.set([groupA, groupB])
    userB.groups.set([groupA])
    return Fixture(users=[userA, userB, userC], groups=[groupA, groupB, groupC])


client = None


def get_client():
    global client
    if client is not None:
        return client

    client = Server.from_source({
        "api": {
            "authentication": {
                "type": "token",
                "bearer": "JWT",
                "header": "X-JWT",
                "token": "..."
            },
            "url": "http://localhost/api/"
        }
    })
    tests = client.spaces_by_name['tests']
    users = tests.resources_by_name['users']


class DjangoIntegrationTestCase(TestCase):
    maxDiff = None

    def test_version(self):
        self.assertEqual(__version__, "0.1.0")

    def test_setup_server(self):
        server = get_server()
        tests = server.spaces_by_name["tests"]
        users = tests.resources_by_name["users"]
        groups = tests.resources_by_name["groups"]
        session = tests.resources_by_name["session"]

        self.assertEqual(groups.id, "tests.groups")
        self.assertEqual(users.id, "tests.users")
        self.assertEqual(users.space.name, "tests")
        self.assertEqual(users.space, tests)
        self.assertEqual(server.url, "http://localhost/api/")
        self.assertEqual(tests.url, "http://localhost/api/tests/")
        self.assertEqual(users.url, "http://localhost/api/tests/users/")

        query1 = tests.query("users" "?take=id,name" "&page:size=10" "&action=get")
        query2 = (
            tests.query.resource("users").take("id", "name").page(size=10).action("get")
        )
        self.assertEqual(query1.state, query2.state)

        query3 = tests.query(
            "?take.users=*,-name"
            "&take.groups=id"
            "&page.users:size=5"
            "&page.users:after=ABC"
            "&sort.groups=-created,id"
            "&where.groups:updated:gte=created"
            "&where.users:name:contains='Joe'"
        )
        query4 = (
            tests.query.take.users("*", "-name")
            .page.users(after="ABC", size=5)
            .take.groups("id")
            .sort.groups("-created", "id")
            .where.groups({"gte": ["updated", "created"]})
            .where.users({"contains": ["name", "'Joe'"]})
        )
        self.assertEqual(query3.state, query4.state)
        self.assertEqual(
            query3.state,
            {
                "take": {
                    "groups": {
                        "sort": ["-created", "id"],
                        "take": {"id": True},
                        "where": {"gte": ["updated", "created"]},
                    },
                    "users": {
                        "page": {"after": "ABC", "size": 5},
                        "take": {"*": True, "name": False},
                        "where": {"contains": ["name", "'Joe'"]},
                    },
                },
                "space": "tests",
            },
        )

        query5 = tests.query("/users/1/groups" "?take=id,name")
        query6 = (
            tests.query.resource("users").id("1").field("groups").take("id", "name")
        )
        self.assertEqual(query5.state, query6.state)
        id = users.get_field("id")
        self.assertEqual(id.resource, users)

        metaspace = server.metaspace
        schemas = [
            SpaceSchema, ResourceSchema, TypeSchema, FieldSchema, ServerSchema
        ]
        self.assertEqual(
            [resource.id for resource in metaspace.resources],
            [s.id for s in schemas]
        )
        self.assertEqual(
            [resource.fields_by_name.keys() for resource in metaspace.resources],
            [s.fields.keys() for s in schemas]
        )

    def test_get_space(self):
        server = get_server()
        tests = server.spaces_by_name["tests"]

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        groupA, groupB, groupC = fixture.groups
        request = Request(userA)

        self.assertEqual(
            tests.query.get(request=request),
            {
                "data": {
                    "users": "./users/",
                    "groups": "./groups/",
                    "session": "./session/",
                }
            },
        )

        get_all = (
            tests.query.take.users("id")
            .take.groups("id")
            .take.session("*")
            .get(request=request)
        )
        self.assertEqual(
            get_all,
            {
                "data": {
                    "users": [{"id": str(userA.id),}, {"id": str(userB.id)}],
                    "groups": [
                        {"id": str(groupA.id)},
                        {"id": str(groupB.id)},
                        {"id": str(groupC.id)},
                    ],
                    "session": {"user": str(userA.id)},
                }
            },
        )

        get_with_filters = (
            tests.query.take.users("id")
            .take.users.groups("id")
            .where.users({"=": ["id", f'"{userA.id}"']})
            .take.groups("id")
            .where.groups({"=": ["id", f'"{groupA.id}"']})
            .get(request=request)
        )
        self.assertEqual(
            get_with_filters,
            {
                "data": {
                    "users": [
                        {
                            "id": str(userA.id),
                            "groups": [{"id": str(groupA.id)}, {"id": str(groupB.id)}],
                        }
                    ],
                    "groups": [{"id": str(groupA.id)}],
                }
            },
        )

    def test_explain_server(self):
        server = get_server()
        meta = server.serialize()
        self.assertEqual(server.query.explain(), {"data": {"server": meta}})
        self.assertEqual(
            meta,
            {
                "version": "0.0.1",
                "url": "http://localhost/api/",
                "spaces": ["tests", self._],
                "can": None,
                "source": None,
                "features": {
                    "take": True,
                    "where": True,
                    "page": {
                        "size": 50,
                        "max_size": 100
                    },
                    "group": True,
                    "sort": True,
                    "inspect": True,
                    "action": True,
                },
                "types": types
            },
        )

    def test_explain_field(self):
        server = get_server()
        tests = server.spaces_by_name["tests"]
        users = tests.resources_by_name["users"]
        groups = users.fields_by_name["groups"]
        self.assertEqual(
            users.query.explain(field="groups"), {"data": {"field": groups.serialize()}}
        )

    def test_explain_resource(self):
        server = get_server()
        tests = server.spaces_by_name["tests"]
        users = tests.resources_by_name["users"]
        self.assertEqual(
            users.query.explain(), {"data": {"resource": users.serialize()}}
        )

    def test_explain_space(self):
        server = get_server()
        tests = server.spaces_by_name["tests"]
        self.assertEqual(tests.query.explain(), {"data": {"space": tests.serialize()}})

    def test_get_server(self):
        server = get_server()

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        groupA, groupB, groupC = fixture.groups
        request = Request(userA)

        self.assertEqual(
            server.query.get(request=request),
            {"data": {"tests": "./tests/", f"{self._}": f"./{self._}/"}},
        )

        response = server.query.get(request=request, response=True)
        self.assertEqual(response.data, {"data": {"tests": "./tests/", f"{self._}": f"./{self._}/"}})
        self.assertEqual(response.code, 200)

        get_all = (
            server.query.take.tests.users("id")
            .take.tests.groups("id")
            .take.tests.session("*")
            .get(request=request)
        )
        self.assertEqual(
            get_all,
            {
                "data": {
                    "tests": {
                        "users": [{"id": str(userA.id),}, {"id": str(userB.id)}],
                        "groups": [
                            {"id": str(groupA.id)},
                            {"id": str(groupB.id)},
                            {"id": str(groupC.id)},
                        ],
                        "session": {"user": str(userA.id)},
                    }
                }
            },
        )

        get_with_filters = (
            server.query.take.tests.users("id")
            .take.tests.users.groups("id")
            .where.tests.users({"=": ["id", f'"{userA.id}"']})
            .take.tests.groups("id")
            .where.tests.groups({"=": ["id", f'"{groupA.id}"']})
            .get(request=request)
        )
        self.assertEqual(
            get_with_filters,
            {
                "data": {
                    "tests": {
                        "users": [
                            {
                                "id": str(userA.id),
                                "groups": [
                                    {"id": str(groupA.id)},
                                    {"id": str(groupB.id)},
                                ],
                            }
                        ],
                        "groups": [{"id": str(groupA.id)}],
                    }
                }
            },
        )

    def test_get_resource_restricted(self):
        """Tests get_resource"""
        server = get_server()
        tests = server.spaces_by_name["tests"]
        users = tests.resources_by_name["users"]
        groups = tests.resources_by_name["groups"]
        session = tests.resources_by_name["session"]

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        request = Request(userB)
        groupA, groupB, groupC = fixture.groups

        ## selecting
        session_get = session.query.get(request=request)
        self.assertEqual(session_get, {"data": {"user": str(userB.id)}})
        session_take_user = session.query.take.user("id", "first_name").get(
            request=request
        )
        self.assertEqual(
            session_take_user,
            {"data": {"user": {"id": str(userB.id), "first_name": userB.first_name}}},
        )

        simple_get = users.query.get(request=request)
        self.assertEqual(
            simple_get,
            {
                "data": [
                    {
                        "id": str(userB.id),
                        "email": userB.email,
                        "first_name": userB.first_name,
                        "last_name": userB.family_name,
                        "name": f"{userB.first_name} {userB.family_name}",
                    }
                ]
            },
        )

        take_id_only = users.query.take("id").get(request=request)
        self.assertEqual(
            take_id_only, {"data": [{"id": str(userB.id)}]}
        )

        dont_take_id = users.query.take("*", "-id", "-name").get(request=request)
        self.assertEqual(
            dont_take_id,
            {
                "data": [
                    {
                        "email": userB.email,
                        "first_name": userB.first_name,
                        "last_name": userB.family_name,
                    }
                ]
            },
        )
        take_nothing = users.query.take("-id").get(request=request)
        self.assertEqual(take_nothing, {"data": [{}]})

        queries = {}
        take_groups = users.query.take("*", "groups", "-name").get(request=request, queries=queries)
        self.assertEqual(
            take_groups,
            {
                "data": [
                    {
                        "id": str(userB.id),
                        "email": userB.email,
                        "first_name": userB.first_name,
                        "last_name": userB.family_name,
                        "groups": [str(groupA.id)]
                    },
                ]
            },
        )

        prefetch_groups = users.query("?take=*,-name&take.groups=*,users").get(
            request=request, queries=queries
        )
        self.assertEqual(
            prefetch_groups,
            {
                "data": [
                    {
                        "id": str(userB.id),
                        "email": userB.email,
                        "first_name": userB.first_name,
                        "last_name": userB.family_name,
                        "groups": [{
                            "id": str(groupA.id),
                            "name": groupA.name,
                            "users": [
                                str(userB.id)
                            ]  # userA is not returned
                        }],
                    },
                ]
            },
        )
        prefetch_deep_query = users.query(
            "?take=*,-name&take.groups=*&take.groups.users=id,groups"
        )
        prefetch_deep = prefetch_deep_query.get(request=request)
        self.assertEqual(
            prefetch_deep,
            {
                "data": [
                    {
                        "id": str(userB.id),
                        "email": userB.email,
                        "first_name": userB.first_name,
                        "last_name": userB.family_name,
                        "groups": [
                            {
                                "id": str(groupA.id),
                                "name": groupA.name,
                                "users": [{
                                    "id": str(userB.id),
                                    "groups": [str(groupA.id)]
                                }],
                                # userA is not returned to userB
                            }
                        ],
                    },
                ]
            },
        )

        ## filtering

        get_where = (
            users.query.take("id")
            .where({"contains": ["first_name", f'"{userB.first_name}"']})
            .get(request=request)
        )
        self.assertEqual(get_where, {"data": [{"id": str(userB.id)}]})

        get_where_related = (
            users.query.take("id").where({"null": "groups"}).get(request=request)
        )
        self.assertEqual(get_where_related, {"data": []})


    def test_get_resource(self):
        """Tests get_resource"""
        server = get_server()
        tests = server.spaces_by_name["tests"]
        users = tests.resources_by_name["users"]
        groups = tests.resources_by_name["groups"]
        session = tests.resources_by_name["session"]

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        request = Request(userA)
        groupA, groupB, groupC = fixture.groups

        # unauthorized user can't see any users
        self.assertEqual(users.query.get(), {'data': []})

        ## selecting
        session_get = session.query.get(request=request)
        self.assertEqual(session_get, {"data": {"user": str(userA.id)}})
        session_take_user = session.query.take.user("id", "first_name").get(
            request=request
        )
        self.assertEqual(
            session_take_user,
            {"data": {"user": {"id": str(userA.id), "first_name": userA.first_name}}},
        )

        simple_get = users.query.get(request=request)
        self.assertEqual(
            simple_get,
            {
                "data": [
                    {
                        "id": str(userA.id),
                        "email": userA.email,
                        "is_superuser": True,
                        "first_name": userA.first_name,
                        "last_name": userA.family_name,
                        "name": f"{userA.first_name} {userA.family_name}",
                    },
                    {
                        "id": str(userB.id),
                        "is_superuser": False,
                        "email": userB.email,
                        "first_name": userB.first_name,
                        "last_name": userB.family_name,
                        "name": f"{userB.first_name} {userB.family_name}",
                    },
                ]
            },
        )

        take_id_only = users.query.take("id").get(request=request)
        self.assertEqual(
            take_id_only, {"data": [{"id": str(userA.id)}, {"id": str(userB.id)}]}
        )

        dont_take_id = users.query.take("*", "-id", "-name").get(request=request)
        self.assertEqual(
            dont_take_id,
            {
                "data": [
                    {
                        "email": userA.email,
                        "first_name": userA.first_name,
                        "is_superuser": True,
                        "last_name": userA.family_name,
                    },
                    {
                        "email": userB.email,
                        "is_superuser": False,
                        "first_name": userB.first_name,
                        "last_name": userB.family_name,
                    },
                ]
            },
        )
        take_nothing = users.query.take("-id").get(request=request)
        self.assertEqual(take_nothing, {"data": [{}, {}]})
        queries = {}
        take_groups = users.query.take("*", "groups", "-name").get(request=request, queries=queries)
        self.assertEqual(
            take_groups,
            {
                "data": [
                    {
                        "id": str(userA.id),
                        "email": userA.email,
                        "is_superuser": True,
                        "first_name": userA.first_name,
                        "last_name": userA.family_name,
                        "groups": [str(groupA.id), str(groupB.id)],
                    },
                    {
                        "id": str(userB.id),
                        "email": userB.email,
                        "is_superuser": False,
                        "first_name": userB.first_name,
                        "last_name": userB.family_name,
                        "groups": [str(groupA.id)],
                    },
                ]
            },
        )

        prefetch_groups = users.query("?take=*,-name&take.groups=*").get(
            request=request
        )
        self.assertEqual(
            prefetch_groups,
            {
                "data": [
                    {
                        "id": str(userA.id),
                        "email": userA.email,
                        "is_superuser": True,
                        "first_name": userA.first_name,
                        "last_name": userA.family_name,
                        "groups": [
                            {
                                "id": str(groupA.id),
                                "name": groupA.name,
                            },
                            {
                                "id": str(groupB.id),
                                "name": groupB.name,
                            },
                        ],
                    },
                    {
                        "id": str(userB.id),
                        "email": userB.email,
                        "is_superuser": False,
                        "first_name": userB.first_name,
                        "last_name": userB.family_name,
                        "groups": [{
                            "id": str(groupA.id),
                            "name": groupA.name,
                        }],
                    },
                ]
            },
        )

        prefetch_deep_query = users.query(
            "?take=*,-name&take.groups=*&take.groups.users=id,groups"
        )
        prefetch_deep = prefetch_deep_query.get(request=request)
        groupA_data = {
            "id": str(groupA.id),
            "name": groupA.name,
            "users": [{
                "id": str(userA.id),
                "groups": [str(groupA.id), str(groupB.id)]
            }, {
                "id": str(userB.id),
                "groups": [str(groupA.id)]
            }],
        }
        groupB_data = {
            "id": str(groupB.id),
            "name": groupB.name,
            "users": [{
                "id": str(userA.id),
                "groups": [str(groupA.id), str(groupB.id)]
            }],
        }
        self.assertEqual(
            prefetch_deep,
            {
                "data": [
                    {
                        "id": str(userA.id),
                        "email": userA.email,
                        "is_superuser": userA.is_superuser,
                        "first_name": userA.first_name,
                        "last_name": userA.family_name,
                        "groups": [groupA_data, groupB_data]
                    },
                    {
                        "id": str(userB.id),
                        "email": userB.email,
                        "is_superuser": userB.is_superuser,
                        "first_name": userB.first_name,
                        "last_name": userB.family_name,
                        "groups": [groupA_data],
                    }
                ]
            },
        )

        ## filtering

        get_where = (
            users.query.take("id")
            .where({"contains": ["first_name", f'"{userA.first_name}"']})
            .get(request=request)
        )
        self.assertEqual(get_where, {"data": [{"id": str(userA.id)}]})

        get_where_related = (
            users.query.take("id").where({"null": "groups"}).get(request=request)
        )
        self.assertEqual(get_where_related, {"data": []})

        ## sorting

        sort_descending = users.query.take("id").sort("-last_name").get(request=request)
        self.assertEqual(
            sort_descending, {"data": [{"id": str(userB.id)}, {"id": str(userA.id)}]}
        )

        sort_ascending = users.query.take("id").sort("last_name").get(request=request)
        self.assertEqual(
            sort_descending, {"data": [{"id": str(userB.id)}, {"id": str(userA.id)}]}
        )

        ## paginating

        page_1_query = users.query.take("id").page(size=1).action('get')
        page_1 = page_1_query.execute(request=request)

        # after is a b64-encoded query, which contains a b64-encoded pagination token
        after = base64.b64encode(json.dumps({"offset": 1}).encode("utf-8")).decode()
        after = page_1_query.page(after=after).encode()

        self.assertEqual(
            page_1,
            {
                "data": [{"id": str(userA.id)}],
                "meta": {"page": {"data": {"after": after, "total": 2}}},
            },
        )
        # to get the next page, pass the entire query back to the server
        # this is helpful with nested pagination links
        page_2 = server.query(f'?query={quote(after)}').execute(request=request)
        self.assertEqual(page_2, {"data": [{"id": str(userB.id)}]})

        # aggregating
        user_stats_query = users.query.group({
            "count": {'count': 'id'},
            'max': {'max': 'email'}
        })
        user_stats = user_stats_query.get(request=request)
        self.assertEqual(
            user_stats, {
                "data": {
                    "count": 2,
                    "max": 'email-14@test.com'
                }
            }
        )


    def test_get_record_restricted(self):
        """Tests get_record as a non-superuser"""
        server = get_server()
        tests = server.spaces_by_name["tests"]
        users = tests.resources_by_name["users"]
        groups = tests.resources_by_name["groups"]

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        groupA, groupB, groupC = fixture.groups
        request = Request(userB)

        ## selecting
        not_found = users.query.get(userA.id, request=request, response=True)
        # 404 is returned instead of 403 to prevent leaking information about this ID
        self.assertEqual(
            not_found.code,
            404
        )

        simple_get = users.query.get(userB.id, request=request)
        self.assertEqual(
            simple_get,
            {
                "data": {
                    "id": str(userB.id),
                    "email": userB.email,
                    "first_name": userB.first_name,
                    "last_name": userB.family_name,
                    "name": f"{userB.first_name} {userB.family_name}",
                }
            },
        )

    def test_get_record(self):
        """Tests get_record as a superuser"""
        server = get_server()
        tests = server.spaces_by_name["tests"]
        users = tests.resources_by_name["users"]
        groups = tests.resources_by_name["groups"]

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        groupA, groupB, groupC = fixture.groups
        request = Request(userA)

        ## selecting
        simple_get = users.query.get(userA.id, request=request)
        self.assertEqual(
            simple_get,
            {
                "data": {
                    "id": str(userA.id),
                    "email": userA.email,
                    "is_superuser": userA.is_superuser,
                    "first_name": userA.first_name,
                    "last_name": userA.family_name,
                    "name": f"{userA.first_name} {userA.family_name}",
                }
            },
        )

        take_id_only = users.query.take("id").get(userA.id, request=request)
        self.assertEqual(take_id_only, {"data": {"id": str(userA.id)}})

        dont_take_id = users.query.take("*", "-id").get(userA.id, request=request)
        self.assertEqual(
            dont_take_id,
            {
                "data": {
                    "email": userA.email,
                    "is_superuser": userA.is_superuser,
                    "first_name": userA.first_name,
                    "last_name": userA.family_name,
                    "name": f"{userA.first_name} {userA.family_name}",
                }
            },
        )

        take_nothing = users.query.take("-id").get(userA.id, request=request)
        self.assertEqual(take_nothing, {"data": {}})

        take_groups = users.query.take("*", "groups").get(userA.id, request=request)
        self.assertEqual(
            take_groups,
            {
                "data": {
                    "id": str(userA.id),
                    "email": userA.email,
                    "is_superuser": userA.is_superuser,
                    "first_name": userA.first_name,
                    "last_name": userA.family_name,
                    "name": f"{userA.first_name} {userA.family_name}",
                    "groups": [str(groupA.id), str(groupB.id)],
                }
            },
        )

        prefetch_groups = users.query("?take=*&take.groups=*,users").get(
            userA.id, request=request
        )
        self.assertEqual(
            prefetch_groups,
            {
                "data": {
                    "id": str(userA.id),
                    "email": userA.email,
                    "first_name": userA.first_name,
                    "is_superuser": userA.is_superuser,
                    "last_name": userA.family_name,
                    "name": f"{userA.first_name} {userA.family_name}",
                    "groups": [
                        {
                            "id": str(groupA.id),
                            "name": groupA.name,
                            "users": [str(userA.id), str(userB.id)],
                        },
                        {
                            "id": str(groupB.id),
                            "name": groupB.name,
                            "users": [str(userA.id)],
                        },
                    ],
                }
            },
        )

        prefetch_deep_query = users.query("?take=*&take.groups=*&take.groups.users=id")
        prefetch_deep = prefetch_deep_query.get(userA.id, request=request)
        self.assertEqual(
            prefetch_deep,
            {
                "data": {
                    "id": str(userA.id),
                    "is_superuser": userA.is_superuser,
                    "email": userA.email,
                    "first_name": userA.first_name,
                    "last_name": userA.family_name,
                    "name": f"{userA.first_name} {userA.family_name}",
                    "groups": [
                        {
                            "id": str(groupA.id),
                            "name": groupA.name,
                            "users": [{"id": str(userA.id)}, {"id": str(userB.id)}],
                        },
                        {
                            "id": str(groupB.id),
                            "name": groupB.name,
                            "users": [{"id": str(userA.id)}],
                        },
                    ],
                }
            },
        )

    def test_get_field(self):
        """Tests get_field"""
        server = get_server()
        tests = server.spaces_by_name["tests"]
        users = tests.resources_by_name["users"]
        session = tests.resources_by_name["session"]
        groups = tests.resources_by_name["groups"]

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        request = Request(userA)
        groupA, groupB, groupC = fixture.groups

        singleton_get = server.query('tests/session/user').get(request=request)
        self.assertEqual(singleton_get, {"data": str(userA.id)})

        ## selecting
        simple_get = users.query.get(userA.id, "first_name", request=request)
        self.assertEqual(simple_get, {"data": userA.first_name})

        take_groups = users.query.get(userA.id, "groups", request=request)
        self.assertEqual(take_groups, {"data": [str(groupA.id), str(groupB.id)]})

        prefetch_groups = users.query("?take=id,name").get(userA.id, "groups", request=request)
        self.assertEqual(
            prefetch_groups,
            {
                "data": [
                    {"id": str(groupA.id), "name": groupA.name},
                    {"id": str(groupB.id), "name": groupB.name},
                ]
            },
        )

        prefetch_deep = users.query("?take=id,name,users&take.users=id").get(
            userA.id, "groups", request=request
        )
        self.assertEqual(
            prefetch_deep,
            {
                "data": [
                    {
                        "id": str(groupA.id),
                        "name": groupA.name,
                        "users": [{"id": str(userA.id),}, {"id": str(userB.id)}],
                    },
                    {
                        "id": str(groupB.id),
                        "name": groupB.name,
                        "users": [{"id": str(userA.id)}],
                    },
                ]
            },
        )

        num_groups_value = users.query(f'{userA.id}/num_groups').get(request=request)
        self.assertEqual(num_groups_value, {'data': userA.groups.count()})

    def test_django_dispatch(self):
        server = get_server()
        fixture = get_fixture()
        userA, userB, userC = fixture.users
        self.client.login(username=userA.email, password=userA.email)
        # get.server
        response = self.client.get('/api/')
        content = json.loads(response.content)
        self.assertEqual(content, {'data': {'tests': './tests/', self._: f'./{self._}/'}})

        # get.space 
        response = self.client.get('/api/tests/')
        content = json.loads(response.content)
        self.assertEqual(content, {'data': {'groups': './groups/', 'session': './session/', 'users': './users/'}})

        # get.resource
        response = self.client.get('/api/tests/users/')
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": [
                    {
                        "id": str(userA.id),
                        "email": userA.email,
                        "is_superuser": True,
                        "first_name": userA.first_name,
                        "last_name": userA.family_name,
                        "name": f"{userA.first_name} {userA.family_name}",
                    },
                    {
                        "id": str(userB.id),
                        "is_superuser": False,
                        "email": userB.email,
                        "first_name": userB.first_name,
                        "last_name": userB.family_name,
                        "name": f"{userB.first_name} {userB.family_name}",
                    },
                ]
            }
        )
        response = self.client.get(f'/api/tests/users/{userA.id}/email/')
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": userA.email
            }
        )

    _ = settings.METASPACE_NAME

    def test_meta_get_fields(self):
        response = self.client.get(
            f'/api/{self._}/fields/?take=id'
        )
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": [
                    {
                        "id": "tests.session.user"
                    },
                    {
                        "id": "tests.groups.id"
                    },
                    {
                        "id": "tests.groups.name"
                    },
                    {
                        "id": "tests.groups.users"
                    },
                    {
                        "id": "tests.groups.created"
                    },
                    {
                        "id": "tests.groups.updated"
                    },
                    {
                        "id": "tests.users.id"
                    },
                    {
                        "id": "tests.users.first_name"
                    },
                    {
                        "id": "tests.users.last_name"
                    },
                    {
                        "id": "tests.users.name"
                    },
                    {
                        "id": "tests.users.email"
                    },
                    {
                        "id": "tests.users.num_groups"
                    },
                    {
                        "id": "tests.users.groups"
                    },
                    {
                        "id": "tests.users.is_superuser"
                    },
                    {
                        "id": "tests.users.created"
                    },
                    {
                        "id": "tests.users.updated"
                    },
                    {
                        "id": "tests.users.location"
                    },
                    {
                        "id": "spaces.server"
                    },
                    {
                        "id": "spaces.url"
                    },
                    {
                        "id": "spaces.name"
                    },
                    {
                        "id": "spaces.can"
                    },
                    {
                        "id": "spaces.resources"
                    },
                    {
                        "id": "resources.id"
                    },
                    {
                        "id": "resources.source"
                    },
                    {
                        "id": "resources.url"
                    },
                    {
                        "id": "resources.name"
                    },
                    {
                        "id": "resources.singleton"
                    },
                    {
                        "id": "resources.description"
                    },
                    {
                        "id": "resources.engine"
                    },
                    {
                        "id": "resources.space"
                    },
                    {
                        "id": "resources.fields"
                    },
                    {
                        "id": "resources.can"
                    },
                    {
                        "id": "resources.parameters"
                    },
                    {
                        "id": "resources.features"
                    },
                    {
                        "id": "resources.labels"
                    },
                    {
                        "id": "resources.label"
                    },
                    {
                        "id": "resources.before"
                    },
                    {
                        "id": "resources.after"
                    },
                    {
                        "id": "resources.abstract"
                    },
                    {
                        "id": "types.name"
                    },
                    {
                        "id": "types.base"
                    },
                    {
                        "id": "types.children"
                    },
                    {
                        "id": "types.container"
                    },
                    {
                        "id": "types.server"
                    },
                    {
                        "id": "fields.id"
                    },
                    {
                        "id": "fields.resource"
                    },
                    {
                        "id": "fields.source"
                    },
                    {
                        "id": "fields.inverse"
                    },
                    {
                        "id": "fields.name"
                    },
                    {
                        "id": "fields.can"
                    },
                    {
                        "id": "fields.url"
                    },
                    {
                        "id": "fields.options"
                    },
                    {
                        "id": "fields.depends"
                    },
                    {
                        "id": "fields.description"
                    },
                    {
                        "id": "fields.example"
                    },
                    {
                        "id": "fields.type"
                    },
                    {
                        "id": "fields.unique"
                    },
                    {
                        "id": "fields.lazy"
                    },
                    {
                        "id": "fields.index"
                    },
                    {
                        "id": "fields.primary"
                    },
                    {
                        "id": "fields.default"
                    },
                    {
                        "id": "server.version"
                    },
                    {
                        "id": "server.url"
                    },
                    {
                        "id": "server.spaces"
                    },
                    {
                        "id": "server.source"
                    },
                    {
                        "id": "server.can"
                    },
                    {
                        "id": "server.features"
                    },
                    {
                        "id": "server.types"
                    }
                ]
            }
        )

    def test_meta_get_resources(self):
        response = self.client.get(
            f'/api/{self._}/resources/?take=id&sort=-name'
        )
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": [{
                    'id': 'tests.users'
                }, {
                    'id': 'types'
                }, {
                    'id': 'spaces'
                }, {
                    'id': 'tests.session'
                }, {
                    'id': 'server'
                }, {
                    'id': 'resources'
                }, {
                    'id': 'tests.groups'
                }, {
                    'id': 'fields'
                }]
             }
        )

        response = self.client.get(
            f'/api/{self._}/resources/?take=id&sort=-name&where:space.name="{self._}"'
        )
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": [{
                    'id': 'types'
                }, {
                    'id': 'spaces'
                }, {
                    'id': 'server'
                }, {
                    'id': 'resources'
                }, {
                    'id': 'fields'
                }]
             }
        )
        response = self.client.get(
            f'/api/{self._}/resources/tests.session/'
        )
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": {
                    "abstract": False,
                    "after": None,
                    "before": None,
                    "can": {
                        "explain": True,
                        "get": True,
                        "login.resource": True,
                        "logout.resource": True,
                    },
                    "description": None,
                    "engine": "django",
                    "features": None,
                    "fields": ["tests.session.user"],
                    "labels": None,
                    "label": None,
                    "id": "tests.session",
                    "name": "session",
                    "parameters": None,
                    "singleton": True,
                    "source": None,
                    "space": "tests",
                    "url": "http://localhost/api/tests/session/"
                }
            }
        )
        response = self.client.get(
            f'/api/{self._}/resources/tests.session/url'
        )
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {"data": "http://localhost/api/tests/session/"}
        )

    def test_meta_get_spaces(self):
        response = self.client.get(
            f'/api/{self._}/spaces/'
        )
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": [{
                    "can": None,
                    "name": "tests",
                    "resources": ["tests.session", "tests.groups", "tests.users"],
                    "server": "http://localhost/api/",
                    "url": "http://localhost/api/tests/"
                }, {
                    "can": None,
                    "name": self._,
                    "resources": ["spaces", "resources", "types", "fields", "server"],
                    "server": "http://localhost/api/",
                    "url": f"http://localhost/api/{self._}/"
                }]
            }
        )

        response = self.client.get(
            f'/api/{self._}/spaces/?where:name="tests"'
        )
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": [{
                    "can": None,
                    "name": "tests",
                    "resources": ["tests.session", "tests.groups", "tests.users"],
                    "server": "http://localhost/api/",
                    "url": "http://localhost/api/tests/"
                }]
            }
        )

        response = self.client.get(
            f'/api/{self._}/spaces/?where:name:contains="t"&take=name'
        )
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": [{
                    "name": "tests",
                }]
            }
        )

        response = self.client.get(
            f'/api/{self._}/spaces/tests/'
        )
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": {
                    "can": None,
                    "name": "tests",
                    "resources": ["tests.session", "tests.groups", "tests.users"],
                    "server": "http://localhost/api/",
                    "url": "http://localhost/api/tests/"
                }
            }
        )

        response = self.client.get(
            f'/api/{self._}/spaces/tests/url/'
        )
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": "http://localhost/api/tests/"
            }
        )

    def test_meta_get_server(self):
        response = self.client.get(
            f'/api/{self._}/server/'
        )
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": {
                    "version": "0.0.1",
                    "url": "http://localhost/api/",
                    "spaces": ["tests", self._],
                    "can": None,
                    "source": None,
                    "features": {
                        "take": True,
                        "where": True,
                        "page": {
                            "size": 50,
                            "max_size": 100
                        },
                        "group": True,
                        "sort": True,
                        "inspect": True,
                        "action": True,
                    },
                    "types": types
                }
            }
        )

        response = self.client.get(f'/api/{self._}/server/spaces')
        content = json.loads(response.content)
        self.assertEqual(
            content,
            {
                "data": ["tests", self._]
            }
        )

    # MVP TODOs:
    # [x] use prefetch for many-related fields instead of ArrayAgg (bugged) 
    # [x] custom prefetcher to support nested pagination
    # [ ] group (aggregation)
    # [ ] hooks (before/after)
    # [ ] add
    # [ ] delete
    # [ ] set/edit
    # [ ] meta executor (get/explain only, for metaspace queries)
    # [ ] documentation

    # post MVP
    # [ ] custom Python methods
    # [ ] API executor (client)
    #   source:
    #       url: api.example.io/v0/users/
    #       authentication:
    #           for: example.io
    #           type: basic | key | token | JWT | cookie
    #           url: api.example.io/v0/login/
    #           method: post
    #           headers:
    #               ...
    #           data:
    #               username:
    #               password:
