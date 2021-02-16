# pyresource

**pyresource** is a Python implementation of a [resource](https://resource.rest) API server.
Currently, there is one implemented resource engine: django (allowing for resources that bind to Django models).
A web engine is in development (allowing for resources that bind to other resource APIs)

Contents:
  * [Definitions](#definitions)
  * [Getting Started](#getting-started)
    * [Installation](#installation-1)
       * [Add settings](#add-settings)
       * [Add server](#add-server)
       * [Mount server](#mount-server)
    * [Add spaces](#add-spaces-1)
       * [V0](#v0)
       * [V1](#v1)
    * [Add resources](#add-resources-1)
       * [Clients](#clients)
       * [Users](#users)
       * [Groups](#groups)
    * [Running the server](#running-the-server-1)
    * [Web requests](#web-requests-1)
    * [Python requests](#python-requests-1)
    * [Authorization](#authorization-1)

## Definitions

- A **resource** is a complex API type, either a *singleton* (referencing one record) or a *collection* (referencing many records)
- A resource is made up of many **fields**
- Each resource belongs to a **space** (a namespace)
- Resources can have **link**-type fields that reference other resources within the same space
- Each space is hosted on a **server** which is exposed at a particular URL
- Users interact with resources by sending **actions** to the server's **endpoints** as HTTP requests
- Each space, resource, and field belonging to a server (and the server itself) has a unique endpoint and URL
- Resource constructs a **query** object for each request from the request URL and body

## Getting Started

This guide walks through each step in creating a small set of resource APIs, assuming you are starting with a Django project

### Installation

- Run the following:
    - 
``` bash
    pip install pyresource
    # ... or "poetry add pyresource"
    # ... or "pipenv add pyresource"
```

#### Add settings

- In your `settings.py`, add `BASE_URL` and use `pyresource.configure` to configure global options:

``` python
    # settings.py
    import pyresource

    # in production, set this to the server hostname
    BASE_URL = os.environ.get('BASE_URL', 'localhost')
    # add default configuration
    pyresource.configure({
        'PAGE_SIZE': 1000,
        'PAGE_TOTAL': False,
        'ENGINE': 'django'
    })
```

#### Add server

- Create `app/resources/server.py`, the entrypoint to your resource server:

``` python
    from django.conf import settings
    from pyresource.server import Server

    server = Server(url=f'{settings.BASE_URL}/api')
```

- Touch `app/resources/__init__.py`

**Note**: all resource definitions for a single server should be defined in one subpackage of your project folder.
The recommended package path is "app.resources" (if your app name is "app").

#### Mount server

- In `app/resources/urls.py` add the lines:

``` python
    from .server import server
    from pyresource.django.urls import get_urlpatterns
    urlpatterns = get_urlpatterns(server)
```

- In your `urls.py`, add the lines:

``` python
    urlpatterns += [
        url(r'^api', include('app.resources.urls'))
    ]
```

**Note**: after this point, you no longer need to configure any additional URLs using Django.
New spaces/resources will automatically be routed to by the server's internal routing.

### Add spaces

#### V0

Create space "v0":

- Create `app/resources/spaces/v0/space.py`:

``` python
    from pyresource.space import Space
    from app.resources.server import server

    v0 = Space(name='v0', server=server)
```

- Touch `app/resources/spaces/__init__.py`
- Touch `app/resources/spaces/v0/__init__.py`

#### V1

- Create `app/resources/spaces/v1/space.py`:

``` python
    from pyresource.space import Space
    from app.resources.server import server

    v1 = Space(name='v1', server=server)
```

- Touch `app/resources/spaces/v1/__init__.py`

### Add resources

#### Clients

- Create `app/resources/spaces/v0/resources/clients.py`:

``` python
    from pyresource.resource import Resource
    from app.spaces.v0.space import v0

    clients = Resource(
        space=v0,
        name='clients',
        model='app.user'       # infer all fields from the model
        fields='*'             # since there is no groups resource,
                               # the "groups" relation will be rendered as an array of objects
    )
```

- Touch `app/resources/spaces/v0/resources/__init__.py`

#### Users

- Create `app/resources/spaces/v1/resources/users.py`:

``` python
    from pyresource.resource import Resource
    from pyresource.types import Types
    from app.spaces.v1.space import v1

    users = Resource(
        name='users',
        model='app.user',
        fields={
            'id': 'id',                 # map individual fields to model fields
            'avatar': 'profile.avatar', # map through a has-one relationship
                                            # this field will be setable by default
                                            # if the field is set and profile does not exist,
                                            # a profile will be created and assigned to the user first
                                            # then the avatar field will be set
            'email': 'email_address',   # remap the name
            'role': {                   # redefine the field (recommended)
                # can be automatically inferred from model:

                'source': 'role',           # the model source
                'description': 'role'       # description
                'type': "number",           # type of the field, including nullability
                'unique': False,            # uniqueness groups or true for self-only
                'index': ['role'],          # index groups or true for self-only
                'primary': False,           # primary key (default: false)
                'default': 2,               # default value
                'options': [{               # field choices
                    "value": 1,
                    "label": "normal",
                }, {
                    "value": 2,
                    "label": "admin",
                    "can": {                # dynamic field choice permissions
                        "set": {"true": ".request.user.is_staff"},
                    }
                },

                # more advanced features:

                # lazy loading
                "lazy": True                # this field is lazy (default False)
                                            # it will not be returned unless requested
                # access control
                # by default, full access
                "can": {
                    'get': {
                        'or': [{
                            'true': '.request.user.is_staff'
                        }, {
                            'true': '.request.user.is_superuser'
                        }]
                        # this field can be viewed by staff or superusers (default All)
                    },
                }
            },
            'groups': 'groups'
        },
        # resource
        can={
            'get': True,
            'delete, add, set': {
                'true': '.request.user.is_superuser'
            }
        },
        features={
            'take': True,
            'where': True,
            'sort': True,
            'page': {
                'max_size': 20
            },
            'group': {
                'operators': [
                    'sum', 'count', 'max'
                ]
            },
            'explain': True,
            'action': True
        },  # default features: where, take, sort, page, group, explain, action
    )
```

- Touch `app/resources/spaces/v1/resources/__init__.py`

#### Groups

Create resource "groups" in space "v1"

Create `app/spaces/v1/resources/groups.py`:

``` python
    from pyresource.resource import Resource

    groups = Resource(
        name='auth.Group',
        model='auth.Group',
        fields='*'
    )
```

### Running the server

- Run the usual Django development server command in a virtual environment (or use `pipenv run` or `poetry run`)

``` bash
    python manage.py runserver
```

### Web requests

Each of the default actions is conveniently mapped to one of the HTTP verbs, but it is always possible to override the action by using the `action` feature.
The following default actions can be made against any endpoint (server, space, resource, field), provided the request has access:

#### get

HTTP method: GET

##### get.server

Read data from the server endpoint through one or more of its spaces.
Example:

```
-->
    GET /api/?take.v0.users=*&take.v1.clients=*

<-- 200
    {
        "data": {
            "v0": {
                "clients": [...]
            },
            "v1": {
                "users": [...]
            }
        }
    }
```

##### get.space

Read data from the space endpoint through one or more of its resources.
Example:
```
-->
    GET /api/v1/?take.users=*&take.groups=*

<-- 200
    {
        "data": {
            "users": [...],
            "groups": [...]
        }
    }
```

##### get.resource

Read data from the resource endpoint through one or more of its fields.
Example:
```
-->
    GET /api/v1/users/?take.groups=*&take.groups=*

<-- 200
    {
        "data": [{
            "id": 1,
            "name": "A",
            "groups": [...]
        }, {
            "id": 2,
            "name": "B",
            "groups": [...]
        }]
    }
```

##### get.field

Read data from the field endpoint.
Example:
```
-->
    GET /api/v1/users/1/groups

<-- 200
    {
        "data": [1, 2, 3]
    }
    
-->
    GET /api/v1/users/1/groups?take=*

<-- 200
    {
        "data": [{
            'id': 1,
            'name': 'groupA'
        }, {
            'id': 2,
            'name': 'groupB'
        }]
    }
```

#### explain

HTTP method: OPTIONS

#### add

HTTP method: POST

#### set

HTTP method: PUT

#### edit

HTTP method: PATCH

#### delete

HTTP method: DELETE

### Python requests

It is also possible to use the Python API to issue requests directly from Python code.
For example, to get data from the server endpoint:

``` python
    from .app.resources.server import server
    from pyresource.request import Request
    from .app.models import User

    user = User.objects.filter(superuser=True).first()
    request = Request(user)
    query = (
        server.query
        .take.users('*')
        .where.users({'in': ['id', [1, 2, 3]]})
        .take.groups('*')
    )
    print(query)
    data = query.get(request=request)
    print(data)
```

Or to get data from a specific resource:

``` python
    # ...
    users = server.spaces_by_name['v0'].resources_by_name['users']
    print(users.query.get(request=request))
```

### Authorization

TODO: explain `can`
