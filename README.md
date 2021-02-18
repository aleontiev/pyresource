# pyresource

**pyresource** is a Python implementation of a [resource](https://resource.rest) API server.
Currently, there is one implemented resource engine: django (allowing for resources that bind to Django models).
A web engine is in development (allowing for resources that bind to other resource APIs)

Contents:
   * [Definitions](#definitions)
   * [Getting Started](#getting-started)
     + [Installation](#installation)
       - [Add settings](#add-settings)
       - [Add server](#add-server)
       - [Mount server](#mount-server)
     + [Add spaces](#add-spaces)
       - [V0](#v0)
       - [V1](#v1)
     + [Add resources](#add-resources)
       - [Clients](#clients)
       - [Users](#users)
       - [Groups](#groups)
     + [Running the server](#running-the-server)
     + [Web requests](#web-requests)
       - [get](#get)
         * [get.resource](#getresource)
         * [get.record](#getrecord)
         * [get.field](#getfield)
         * [get.space](#getspace)
         * [get.server](#getserver)
       - [add](#add)
         * [add.resource](#addresource)
         * [add.record](#addrecord)
         * [add.field](#addfield)
         * [add.space](#addspace)
         * [add.server](#addserver)
       - [set](#set)
         * [set.resource](#setresource)
         * [set.record](#setrecord)
         * [set.field](#setfield)
         * [set.space](#setspace)
         * [set.server](#setserver)
       - [edit](#edit)
         * [edit.resource](#editresource)
         * [edit.record](#editrecord)
         * [edit.field](#editfield)
         * [edit.space](#editspace)
         * [edit.server](#editserver)
       - [delete](#delete)
         * [delete.resource](#deleteresource)
         * [delete.record](#deleterecord)
         * [delete.field](#deletefield)
         * [delete.space](#deletespace)
         * [delete.server](#deleteserver)
       - [explain](#explain)
         * [explain.resource](#deleteresource)
         * [explain.record](#deleterecord)
         * [explain.field](#deletefield)
         * [explain.space](#deletespace)
         * [explain.server](#deleteserver)
     + [Python requests](#python-requests)
   * [Getting deeper](#getting-deeper)
     + [Authentication](#authentication)
     + [Authorization](#authorization)
     + [Expressions](#expressions)
       - [Control flow](#control-flow)
       - [Arithmetic operations](#arithmetic-operations)
       - [Logic operations](#logic-operations)
       - [List operations](#list-operations)
       - [String operations](#string-operations)
       - [Object operations](#object-operations)
       - [Datetime operations](#datetime-operations)
       - [Manual escaping](#manual-escaping)
       - [Custom operations](#custom-operations)
     + [Hooks](#hooks)

## Definitions

- A **resource** is a complex API type, either a *singleton* (referencing one record) or a *collection* (referencing many records)
- A resource is made up of many **fields** which themselves have meta fields, including a JSONSchema **type**
- Each resource belongs to a **space** (namespace)
- Resources can have **link** fields that reference other resources within the same space
- Each space is hosted on a **server** which is exposed at a particular URL
- Users interact with resources by sending **actions** to the server as HTTP requests
- Each space, resource, and field belonging to a server (and the server itself) has a unique **endpoint** and URL
- Resource constructs a **query** object for each request from the request path, querystring, and body
- Certain querystring parameter groups called **features** are given special treatment
- Each server has a meta space called "." that contains meta resources for `resources`, `spaces`, `server`, `fields`, and `types`

## Getting Started

This guide walks through each step in creating a small set of resource APIs, assuming you are starting with a Django project

### Installation

- Run the following:
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
                'source': {                # the name of the underlying model field, or an expression
                    'lower': 'role'
                },
                'description': 'role'       # description/help-text
                'type': ["null", "number"], # JSONSchema+ type of the field, including nullability
                'unique': False,            # uniqueness groups or true for self-only
                'index': ['role'],          # index groups or true for self-only
                'primary': False,           # whether or not this is a primary key
                'default': 2,               # default value
                'options': [{               # choices/options
                    "value": 1,
                    "label": "normal",
                }, {
                    "value": 2,
                    "label": "admin",
                    "can": {                # option-specific access controls
                        "set": {"true": ".request.user.is_staff"},
                    }
                },

                # more advanced features independent from model layer:
                "lazy": True                # this field will not be returned unless requested
                "can": {                    # field-specific access control
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
        # resource access control
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
            'inspect': True,
            'action': True
        }
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

The `get` action is an intent to read data from the server.
It is associated with the HTTP method "GET" and has the following manifestations:

##### get.resource

The `get.resource` action is an intent to read data from the resource endpoint through one or more of its fields.

Examples:

Get users, default fields:
```
-->
    GET /api/v1/users/
    
<-- 200
    {
        "data": [{
            "id": 1,
            "name": "A",
            "groups": [{"id": 1}]
        }, {
            "id": 2,
            "name": "B",
            "groups": [{"id": 1}, {"id": 2}]
        }, {
            "id": 3,
            "name": "C",
            "groups": [{"id": 1}, {"id": 2}, {"id": 3}]
        }]
    }
```

Get users, `id` and `name` fields only:

```
-->
    GET /api/v1/users/?take=id,name

<-- 200
    {
        "data": [{
            "id": 1,
            "name": "A",
            "groups": [{"id": 1}]
        }, {
            "id": 2,
            "name": "B",
            "groups": [{"id": 1}, {"id": 2}]
        }]
    }
```

Get users whose name starts with "A", default fields except `groups`:
```
-->
    GET /api/v1/users/?where:name:starts=A&take=*,-groups

<-- 200
    {
        "data": [{
            "id": 1,
            "name": "A"
        }]
    }
```

Get count and max ID across all users:
```
-->
    GET /api/v1/users/?group:count:num=*&group:max:max_id=id
<-- 200
    {
        "data": {
            "num": 3,
            "max_id": 
        }
    }
```
**Note**: whenever `group` is used, the result is expected to be a dictionary with one value for each aggregation
If `group` is not being used, all queries are subject to pagination in order to prevent the API server from attempting to retrieve and serialize extremely large datasets.

Get all users with `id` and `groups.id` in pages (and sub-pages) of size 2:
```
-->
    GET /api/v1/users/?take.groups=id&page:size=2&page.groups:size=2
<-- 200
    {
        "data": [{
            "id": 1,
            "groups": [{
                "id": 1,
            }, {
                "id": 2
            }]
        }, {
            "id": 2,
            "groups": [{
                "id": 1,
            }, {
                "id": 2
            }]
        }],
        "meta": {
            "page": {
                "data": {
                    "next": "...tokenA..."
                },
                "data.0.groups": {
                    "next": "...tokenB..."
                },
                "data.1.groups": {
                    "next": "...tokenC..."
                }
            }
        }
    }
```

**Note**: When creating pagination links, resource uses base64-encoded **request tokens** which are returned for each paginated data `path` under `meta.page.path.next`.
To use these tokens, make a POST request to the server endpoint that includes a JSON encoded object with the token provided under the key "query".

Get the next page of user data from the previous request:
```
-->
    POST /api/
    {"query": "...tokenA...}
    
<-- 200
    {
        "data": [{
            "id": 3,
            "groups": [{
                "id": 1,
            }, {
                "id": 2
            }]
        }, {
            "id": 4,
            "groups": [{
                "id": 1,
            }, {
                "id": 2
            }]
        }],
        "meta": {
            "page": {...}
        }
    }

```

**Note**: resource will only return pagination metadata if a next page exists, otherwise it will not return anything.
Clients can therefore expect that there are more pages of data for any given request/response only if pagination tokens appear in `meta.page`.

##### get.record

The `get.record` action is an intent to read data from the record endpoint through one or more of the resource's fields.

Examples:

Get data for user 1:
```
-->
    GET /api/v1/users/1/

<-- 200
    {
        "data": {
            "id": 1,
            "name": "userA",
            "groups": [1, 2]
        }
    }
```

**Note**: features like `where`, `sort`, `take` work here too!

Get data for user 1, return groups starting with the letter "A", exclude the name field:
```
-->
    GET /api/v1/users/1/?where.groups:name:contains=A&take=*,-name

<-- 200
    {
        "data": {
            "id": 1,
            "groups": [1]
        }
    }
```

##### get.field

The `get.field` action is an intent to read data from the field endpoint for a specific field.

Examples:

Get group IDs for user 1:
```
-->
    GET /api/v1/users/1/groups

<-- 200
    {
        "data": [1, 2]
    }
```

**Note**: features like `where`, `sort`, and `take` are available for link fields.


Get group IDs for user 1 where name startswith letter "A"
```
-->
    GET /api/v1/users/1/groups?where:name:starts=A

<-- 200
    {
        "data": [1]
    }

```

**Note**: if `take` is specified, related data is also prefetched.

Get group data for user 1's groups:
```
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

##### get.space

The `get.space` action is an intent to read data from the space endpoint through one or more of its resources.

Get `users` and `groups` from `v1`:
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

##### get.server

The `get.server` action is an intent to read data from the server endpoint through one or more of its spaces and their resources.

Get `users` from `v0` and also `clients` from `v1`:
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

#### add

The `add` action is an intent to add data to one or more resources.
It is associated with the HTTP method "POST" and has the following manifestations:

#### add.resource

The `add.resource` action is an intent to add data for a particular resource.

Create a user:
```
-->
    POST /api/v1/users?take=*
    {
        "data": {
            "name": "user A"
        }
    }
    
<-- 201
    {
        "data": {
            "id": 123,
            "name": "user A",
            "created": "2020-01-01T00:00:00Z"
        }
    }
```

Create multiple users (one succeeds and one fails):
```
-->
    POST /api/v1/users?take=*
    {
        "data": [{
            "name": "user A"
        }, {
            "name": "user B"
        }]
    }
    
<-- 400
    {
        "data": [{
            "id": 123,
            "name": "user A",
            "created": "2020-01-01T00:00:00Z"
        }],
        "errors": {
            "data.1": {
                "name": ["there is already a user with name 'user B'"]
            }
        }
    }
```

Create multiple users, all-or-nothing (atomic):
```
-->
    POST /api/v1/users?take=*&atomic
    {
        "data": [{
            "name": "user A"
        }, {
            "name": "user B"
        }, {
            "name": "user C"
        }]
    }
    
<-- 400
    {
        "errors": {
            "data.0": "succeeded, then rolled back due to error in data.1"
            "data.1": {
                "name": ["there is already a user with name 'user B'"]
            },
            "data.2": "skipped due to error in data.1"
        }
    }
```

#### add.field

The `add.field` action is an intent to add-and-link a related object; it is only supported for link fields.

Create a group and associate it with user 1:
```
-->
    POST /api/v1/users/1/group?take=*
    {
        "data": {
            "name": "test group"
        }
    }
    
<-- 201
    {
        "data": {
            "id": 123,
            "name": "test group",
            "created": "2020-01-01T00:00:00Z"
        }
    }
```

#### add.record

The `add.record` action is not implemented

##### add.space

The `add.space` action is an intent to add data from the space endpoint through one or more of its resources.

Add `users` and `groups` in the `v1` space and return them:
```
-->
    POST /api/v1/?take.users=*&take.groups=*
    {
        "data": {
            "users": [{
                "name": "john"
            }],
            "groups": [{
                "name": "A"
            }, {
                "name": "B"
            }]
        }
    }

<-- 201
    {
        "data": {
            "users": [...],
            "groups": [...]
        }
    }
```

##### add.server

The `add.server` action is an intent to add data from the server endpoint through one or more of its spaces and their resources.

Add `v0.users` and also `v1.clients`:
```
-->
    POST /api/
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
    
<-- 201
```

#### set

The `set` action is an intent to modify data in one or more resources.
It is associated with the HTTP method "PUT" and has the following manifestations:

#### set.resource

The `set.resource` action is an intent to modify data in bulk for a particular resource.

Update multiple users by ID (one succeeds and one fails):
```
-->
    PUT /api/v1/users/?take=*
    {
        "data": [{
            "id": 1,
            "name": "user A"
        }, {
            "id": 2,
            "name": "user B"
        }]
    }
    
<-- 400
    {
        "data": [{
            "id": 123,
            "name": "user A",
            "created": "2020-01-01T00:00:00Z",
            "updated": "2020-01-02T00:00:00Z"
        }],
        "errors": {
            "data.1": {
                "name": ["there is already a user with name 'user B'"]
            }
        }
    }
```

Update multiple users by ID, all-or-nothing (atomic):
```
-->
    PUT /api/v1/users?take=*&atomic
    {
        "data": [{
            "id": 1,
            "name": "user A"
        }, {
            "id": 2,
            "name": "user B"
        }, {
            "id": 3,
            "name": "user C"
        }]
    }
    
<-- 400
    {
        "errors": {
            "data.0": "succeeded, then rolled back due to error in data.1"
            "data.1": {
                "name": ["there is already a user with name 'user B'"]
            },
            "data.2": "skipped due to error in data.1"
        }
    }
```

Update all users:
```
-->
    PUT /api/v1/users/
    {
        "data": {
            "name": "userA"
        }
    }
    
<-- 200
    {
        "data": 150
    }
```

**Note**: instead of the data, a count of updated records is returned for bulk update operations

#### set.field

The `set.field` action is an intent to set a particular field to a new value.

Set the name of a user
```
-->
    PUT /api/v1/users/1/name
    {
        "data": "user A"
    }
    
<-- 200
```

#### set.record

The `set.record` action is an intent to modify data for a particular record.

Update a user:
```
-->
    PUT /api/v1/users/1/?take=name,updated
    {
        "data": {
            "name": "user A"
        }
    }
    
<-- 200
    {
        "data": {
            "name": "user A",
            "updated": "2020-01-01T00:00:00Z"
        }
    }
```


##### set.space

The `set.space` action is an intent to update data from the space endpoint through one or more of its resources.

Set `v1/users/1` and `v1/groups/1` and return them:
```
-->
    PUT /api/v1/?take.users=*&take.groups=*
    {
        "data": {
            "users": [{
                "id": 1,
                "name": "john"
            }],
            "groups": [{
                "id": 1,
                "name": "A"
            }]
        }
    }

<-- 200
    {
        "data": {
            "users": [...],
            "groups": [...]
        }
    }
```

##### set.server

The `set.server` action is an intent to update data from the server endpoint through one or more of its spaces and their resources.

Set `v0/users/1` and also `v1/clients/2`:
```
-->
    PUT /api/
    {
        "data": {
            "v0": {
                "clients": [{
                    "id": 2,
                    "name": "A"
                }]
            },
            "v1": {
                "users": [{
                    "id": 1,
                    "name": "B"
                }]
            }
        }
    }
    
<-- 200
```

#### edit

The `edit` action is an intent to partially modify data in one or more records in one or more resources.
It is associated with the HTTP method "PATCH" and has the following manifestations:

#### edit.resource

The `edit.resource` action is an intent to modify data in bulk for a particular resource.

Update multiple users by ID (one succeeds and one fails):
```
-->
    PATCH /api/v1/users/?take=*
    {
        "data": [{
            "id": 1,
            "name": "user A"
        }, {
            "id": 2,
            "name": "user B"
        }]
    }
    
<-- 400
    {
        "data": [{
            "id": 123,
            "name": "user A",
            "created": "2020-01-01T00:00:00Z",
            "updated": "2020-01-02T00:00:00Z"
        }],
        "errors": {
            "data.1": {
                "name": ["there is already a user with name 'user B'"]
            }
        }
    }
```

Update multiple users by ID, all-or-nothing (atomic):
```
-->
    PATCH /api/v1/users?take=*&atomic
    {
        "data": [{
            "id": 1,
            "name": "user A"
        }, {
            "id": 2,
            "name": "user B"
        }, {
            "id": 3,
            "name": "user C"
        }]
    }
    
<-- 400
    {
        "errors": {
            "data.0": "succeeded, then rolled back due to error in data.1"
            "data.1": {
                "name": ["there is already a user with name 'user B'"]
            },
            "data.2": "skipped due to error in data.1"
        }
    }
```

Update all users:

```
-->
    PATCH /api/v1/users/
    {
        "data": {
            "name": "userA"
        }
    }
    
<-- 200
    {
        "data": 150
    }
```

**Note**: instead of the data, a count of updated records is returned for bulk update operations

#### edit.field

The `edit.field` action allows for linking and unlinking related resources. TODO

#### edit.record

The `edit.record` action is an intent to modify data for a particular record.

Update a user:
```
-->
    PUT /api/v1/users/1/?take=name,updated
    {
        "data": {
            "name": "user A"
        }
    }
    
<-- 200
    {
        "data": {
            "name": "user A",
            "updated": "2020-01-01T00:00:00Z"
        }
    }
```


##### edit.space

The `edit.space` action is an intent to update data from the space endpoint through one or more of its resources.

Edit `v1/users/1` and `v1/groups/1` and return them:
```
-->
    PATCH /api/v1/?take.users=*&take.groups=*
    {
        "data": {
            "users": [{
                "id": 1,
                "name": "john"
            }],
            "groups": [{
                "id": 1,
                "name": "A"
            }]
        }
    }

<-- 200
    {
        "data": {
            "users": [...],
            "groups": [...]
        }
    }
```

##### edit.server

The `edit.server` action is an intent to update data from the server endpoint through one or more of its spaces and their resources.

Edit `v0/users/1` and also `v1/clients/2`:
```
-->
    PATCH /api/
    {
        "data": {
            "v0": {
                "clients": [{
                    "id": 2,
                    "name": "A"
                }]
            },
            "v1": {
                "users": [{
                    "id": 1,
                    "name": "B"
                }]
            }
        }
    }
    
<-- 200
```

#### delete

HTTP method: DELETE

#### explain

HTTP method: OPTIONS

## Getting deeper

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

### Authentication

Resource is authentication-agnostic and can work with any authentication provider/middleware.
Authentication is not checked explicitly, but may be required indirectly during authorization checks.

### Authorization

Resource uses a flexible access control model that is based on an attribute called `can` that exists on `server`, `space`, `resource`, and `field`:

- If a resource does not specify the `can` attribute, all actions will be allowed for all requests (open permissions, the default behavior)
- If a resource does specify the `can` attribute, then:
    - `can` must be an object with action-keys and expression-values
    - actions against this resource will only be allowed if the expression-value for a matching action-key evaluates to True or to an expression (closed permissions)
    - if an expression-value evaluates to an expression (rather than a boolean), that expression is applied as a query-filter to the resource (partial access controlled by filters)
- Fields may also define `can` (to limit access to fields in certain contexts)
- Field options may also define `can` (to limit access to setting options)
- Spaces may also define `can` (to limit access to space-wide queries)
- Servers may also define `can` (to limit access to server-wide queries)

### Expressions

Many resource and field attributes support expressions that can be used to further refine resource declarations, such as:
- `resource.can`
- `resource.before`
- `resource.after`
- `resource.source`
- `field.default`
- `field.source`
- `field.can`
- `field.options.can`

Expressions follow these principles:
- All JSON values are considered valid expressions
- Any expression is either a literal, an identifier, or an operator
- A literal expression is either a boolean, a number, a list, a string that starts and ends with ' (single-quote), a dictionary with more than one key, or the empty dictionary
- An identifier expression is a string that is not a literal string
- An operator expression is a dictionary with a single key (the operator name) and value either:
    - a list of expressions (list argument style), or
    - a dictionary of expressions (keyword argument style), or
    - a single literal or identifier expression (single argument style)

Resource supports many built-in operators:

#### Control flow

- looping with `each`:
``` json
{
    "each": {
        "in": "...expression...",
        "as": "...expression...",
        "do": "...expression..."
    }
}
```
- branching with `case`:
``` json
{
    "case": [{
        "if": [
            "...expression...",
            "...expression..."
        ]
    }, {
        "if": [
            "...expression...",
            "...expression..."
        ]
    }, {
        "else": "...expression..."
    }]
}
```
- aliasing with `with`:
``` json
{
    "with": {
        "as": [{
            "name": "...expression...",
            "value": "...expression..."
        }, "..."],
        "get": "...expression..."
    }
}
```

- layering with `coalesce`:
``` json
{
    "coalesce": ["...expression...", "...", "...expression..."]
}
```

#### Arithmetic operations

- addition, list/string/object concatenation/append/merge: `+`:
``` json
{
    "+": ["...expression...", "...", "...expression..."]
}
```
- subtraction, list/object removal: `-`:
``` json
{
    "-": ["...expression...", "...", "...expression..."]
}
```
- other math operations, list/object removal (`-`):
``` json
{
    "/, mod, power, round": ["...expression...", "...expression..."]
}
```
- numeric unary: `abs`, `ceil`, `floor`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`
- numeric generators: `pi`, `e`
- numeric variadic: `max`, `min`, `avg`, `deviation`

#### Logic operations

- unary negation:
``` json
{
    "not": "...expression..."
}
```
- unary predicates:
``` json
{
    "true, false, null, empty": "...expression..."
}
```
- comparison:
``` json
{
    "=, >, <=, >=, =, !=": ["...expression...", "...expression..."]
}
```

#### List operations

- list reductions: `contains`, `any`, `all`, `index`, `count`, `reduce`, `join`
``` json
[{
    "index, count, contains": ["...expression...", "...expression..."]
}, {
    "any, all": {
        "from": "...expression...",
        "as": "...expression...",
        "where": "...expression..."
    }
},
{
    "reduce": {
        "from": "...expression...",
        "as": "...expression...",
        "accumulator": "...expression...",
        "initial": "...expression...",
        "reducer": "...expression..."
    }
}]
```

- list manipulations: `distinct`, `filter`, `bucket`, `map`, `key`, `sort`, `slice`, `reverse`, `max`, `min`:
``` json
[{
    "filter": {
        "in": "...expression...",
        "as": "...expression...",
        "where": "...expression..."
    }
},
{
    "map": {
        "in": "...expression...",
        "as": "...expression...",
        "map": "...expression..."
    }
},
{
    "sort, key, bucket": {
        "in": "...expression...",
        "as": "...expression...",
        "by": "...expression..."
    }
},
{
    "slice": ["...expression...", "...expression..."]
},
{
    "max, min, distinct, reverse": "...expression..."
}]
```

#### String operations

- string manipulations: `format`, `replace`, `slice`, `trim`, `upper`, `lower`, `title`, `split`, `reverse`:
``` json
[
{
    "format": "...expression..."
},
{
    "replace": {
        "in": "...expression...",
        "find": "...expression...",
        "replace": "...expression..."
    }
},
{
    "slice": ["...expression...", "...expression..."]
},
{
    "split": ["...expression...", "...expression..."]
},
{
    "reverse, lower, title, upper, trim": "...expression..."
}]
```
- string reductions: `contains`, `index`, `count`
(same interface as with lists; the string is treated like a character-list as in Python)

#### Object operations

- object manipulations: `keys`, `values`, `items`
``` json
{
    "keys, values, items": "...expression..."
}
```

#### Datetime operations

``` json
{
    "today, now": []
}
```

#### Manual escaping

- evaluating arguments literally
``` json
{
    "literal": "any"
}
```

- evaluating argument as an identifier
``` json
{
    "identifier": "string"
}
```

- evaluting argument as an object:
``` json
{
    "object": "object"
}
```

#### Custom operations

You can also customize Resource by adding your own operators.

The only requirements are:
- an operator name
- whether or not the operator can take arguments as a single value, as a list, and/or as a dict (any one, two, or all three)
- a Python method or import string referencing a function (ideally free of any side effects for performance reasons)
  
### Hooks

Resource provides two properties that support customizing the behavior around built-in actions:
- `before` is run before the given action(s)
- `after` is run after the given action(s)
