from pyresource.server import Server
from pyresource.space import Space
from pyresource.resource import Resource

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

    def logout(resource, request, query, data):
        pass

    def change_password(resource, request, query, data):
        pass

    def login(resource, request, query, data):
        if query.state.get("action") not in {"add", "set"}:
            return request.user

        if not data or not isinstance(data, dict) or 'username' not in data or 'password' not in data:
            raise BadRequest("session.login: must provide a data object with 'username' and 'password'")

        username = data['username']
        password = data['password']
        if not authenticate(username, password):
            raise BadRequest("session.login: username and password are not correct")
        return True

    # PUT /session/?take=user {"data": {"login": {"username": ..., "password": ...}}
    # -> {"data": {"user": ...}}

    # or

    # PUT /session/login?take=. {"data": {"username": ..., "password": ...}}
    # -> {"data": {}}
    session = Resource(
        id="tests.session",
        name="session",
        space=tests,
        singleton=True,
        can={
            "get": True,
            "set": True,
            "explain": True
        },
        fields={
            "user": {
                "type": ["null", "@users"],
                "source": ".request.user",
                "can": {"set": False, "get": True}
            },
            "login": {
                "type": ["null", "object"],
                "source": login,
                "can": {"get": False, "set": True}
            },
            "logout": {
                "type": "null",
                "source": logout,
                "can": {"get": False, "set": True}
            }
        },
    )
    groups = Resource(
        id="tests.groups",
        name="groups",
        source={
            "queryset": {
                "model": "tests.group",
                "where": "is_active"
            }
        },
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
            "location": {"lazy": True}
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
    server.setup()
    return server
