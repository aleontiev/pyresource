"""Tests on Django engine"""
import base64
import json
from django.test import TestCase
from pyresource import __version__
from pyresource.space import Space
from pyresource.resource import Resource
from pyresource.server import Server
from pyresource.schemas import (
    SpaceSchema,
    ResourceSchema,
    FieldSchema,
    ServerSchema,
    TypeSchema
)
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
    userA = User.make(family_name="A", first_name="Alex", is_superuser=True)
    userB = User.make(family_name="B", first_name="Bay")
    userC = User.make(is_active=False, first_name="Inactive", family_name="I")
    groupA = Group.make(name="A")
    groupB = Group.make(name="B")
    groupC = Group.make(name="C")
    userA.groups.set([groupA, groupB])
    userB.groups.set([groupA])
    return Fixture(users=[userA, userB, userC], groups=[groupA, groupB, groupC])


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
    server = Server(url="http://localhost/api/",)

    tests = Space(name="tests", server=server)

    def login(resource, request, query):
        api_key = query.state("body").get("api_key")
        api_key = json.loads(str(base64.b64decode(api_key)))
        if authenticate(username, password):
            pass

    def logout(resource, request, query):
        pass

    def change_password(resource, request, query):
        pass

    session = Resource(
        id="tests.session",
        name="session",
        space=tests,
        singleton=True,
        can={"login": True, "logout": True, "get": True, "explain": True},
        fields={"user": {"type": ["null", "@users"], "source": ".request.user"},},
        actions={
            "login": {
                "method": login,
                "fields": {
                    "username": {"type": "string", "can": {"get": False}},
                    "password": {"type": "string", "can": {"get": False}},
                    "status": {"type": "string", "can": {"set": False}},
                },
            },
            "logout": logout,
        },
    )
    groups = Resource(
        id="tests.groups",
        name="groups",
        source={"queryset": {"model": "tests.group", "where": "is_active"}},
        space=tests,
        fields={
            "id": "id",
            "name": "name",
            "users": {
                "source": {"queryset": {"field": "users", "sort": "created"}},
                "lazy": True,
                "can": {"set": False},
            },
            "created": {"lazy": True, "can": {"set": False}},
            "updated": {"lazy": True, "can": {"set": False}},
        },
        can={
            "*": ".request.user.is_superuser",
            "get": {"=": ["users", ".request.user.id"]},
        },
    )

    users = Resource(
        id="tests.users",
        name="users",
        source={
            "queryset": {
                "model": "tests.user",
                "where": "is_active",
                "sort": "created",
            }
        },
        space=tests,
        fields={
            "id": "id",
            "first_name": "first_name",
            "last_name": "family_name",  # renamed field
            "name": {
                "type": "string",
                "source": {"concat": ["first_name", '" "', "family_name"],},
                "can": {"set": False},
            },
            "email": "email",
            "num_groups": {
                "source": {
                    "count": "groups"
                },
                "type": "number",
                "lazy": True,
                "can": {"set": False}
            },
            "groups": {
                "lazy": True,
                "can": {
                    "set": {"=": [".query.action", '"add"']},
                    # can only set if the new value is smaller {'>': ['.changes.groups', 'groups']}
                    # can only set if name is not changing {'null': '.changes.name'}
                    "add": True,
                    "prefetch": True,
                },
                "source": {
                    "queryset": {
                        "field": "groups",
                        "sort": "name",
                        "where": "is_active"
                    }
                },
            },
            "is_superuser": {
                "depends": {
                    "or": [
                        ".request.user.is_superuser",
                        ".request.user.is_staff"
                    ]
                }
            },
            "created": {"lazy": True, "default": {"now": {}}, "can": {"set": False}},
            "updated": {"lazy": True, "default": {"now": {}}, "can": {"set": False}},
        },
        can={
            "*": ".request.user.is_superuser",
            "get, change-password": {"=": ["id", ".request.user.id"]},
        },
        before={
            "change-password": {"check": {"=": ["confirm_password", "new_password"]}}
        },
        actions={
            "change-password": {
                "method": change_password,
                "fields": {
                    "old_password": {"type": "string", "can": {"get": False}},
                    "new_password": {
                        "type": {"type": "string", "min_length": 10,},
                        "can": {"get": False},
                    },
                    "confirm_password": {"type": "string", "can": {"get": False}},
                    "changed": {"type": "boolean", "can": {"set": False}},
                },
            }
        },
    )
    location = Resource(
        id="tests.users",
        name="users",
        space=tests,
        source={"queryset": {"model": "tests.location", "sort": "created"}},
        fields="*",
    )
    server.root  # noqa
    return server


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
            '&where.users:name:contains="Joe"'
        )
        query4 = (
            tests.query.take.users("*", "-name")
            .page.users(after="ABC", size=5)
            .take.groups("id")
            .sort.groups("-created", "id")
            .where.groups({"gte": ["updated", "created"]})
            .where.users({"contains": ["name", '"Joe"']})
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
                        "where": {"contains": ["name", '"Joe"']},
                    },
                },
                "space": "tests",
            },
        )

        query5 = tests.query("/users/1/groups" "?take=id,name")
        query6 = (
            tests.query.resource("users").record("1").field("groups").take("id", "name")
        )
        self.assertEqual(query5.state, query6.state)
        id = users.get_field("id")
        self.assertEqual(id.resource, users)

        root = server.root
        schemas = [
            SpaceSchema, ResourceSchema, TypeSchema, FieldSchema, ServerSchema
        ]
        self.assertEqual(
            [resource.id for resource in root.resources],
            [s.id for s in schemas]
        )
        self.assertEqual(
            [resource.fields_by_name.keys() for resource in root.resources],
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
                "spaces": ["tests", "."],
                "can": None,
                "features": {
                    "take": True,
                    "where": True,
                    "page": {"size": 50, "max_size": 100},
                    "group": True,
                    "sort": True,
                    "inspect": True,
                    "action": True,
                },
                "types": [],
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
            {"data": {"tests": "./tests/", ".": "././"}},
        )

        response = server.query.get(request=request, response=True)
        self.assertEqual(response.data, {"data": {"tests": "./tests/", ".": "././"}})
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

        take_groups = users.query.take("*", "groups", "-name").get(request=request)
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
            request=request
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

        take_groups = users.query.take("*", "groups", "-name").get(request=request)
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

        page_1 = users.query.take("id").page(size=1).get(request=request)
        after = base64.b64encode(json.dumps({"offset": 1}).encode("utf-8"))
        self.assertEqual(
            page_1,
            {
                "data": [{"id": str(userA.id)}],
                "meta": {"page": {"data": {"after": after, "total": 2}}},
            },
        )
        page_2 = users.query.take("id").page(size=1, after=after).get(request=request)
        self.assertEqual(page_2, {"data": [{"id": str(userB.id)}]})

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
        groups = tests.resources_by_name["groups"]

        fixture = get_fixture()
        userA, userB, userC = fixture.users
        request = Request(userA)
        groupA, groupB, groupC = fixture.groups

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

    # MVP TODOs:
    # [x] use prefetch for many-related fields instead of ArrayAgg (bugged) 
    # [ ] group (aggregation)
    # [ ] hooks (before/after)
    # [ ] add
    # [ ] delete
    # [ ] set/edit
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
    # [ ] resource executor (get/explain only, for root space queries)
    # [ ] documentation

    # post MVP
    # - custom properties
