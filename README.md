# django-resource

**django-resource** is an implementation of [Resource](https://resource.rest) for Django.

Contents:
  * [Getting Started](#getting-started)
     * [Using DJ](#using-dj)
        * [Installation](#installation)
        * [Adding spaces](#adding-spaces)
        * [Adding resources](#adding-resources)
        * [Running the server](#running-the-server)
     * [Using pip, pipenv, or poetry](#using-pip-pipenv-or-poetry)
        * [Installation](#installation-1)
           * [Add to INSTALLED APPS](#add-to-installed-apps)
           * [Add to settings](#add-to-settings)
           * [Add core packages](#add-core-packages)
           * [Add server](#add-server)
           * [Mount URL](#mount-url)
        * [Adding spaces](#adding-spaces-1)
           * [V0](#v0)
           * [V1](#v1)
        * [Adding resources](#adding-resources-1)
           * [Clients](#clients)
           * [Users](#users)
           * [Groups](#groups)
        * [Running the server](#running-the-server-1)

## Getting Started

### Using DJ

#### Installation

You can add this to your project with [DJ](https://djay.io), a developer utility tool for Django that wraps pyenv, virtualenv, pip, and poetry.
It allows you to quickly add `django-resource` to your project and set up your own resources with the CLI:

``` bash 
    dj add django-resource
```

The above command will run an initialization blueprint to automatically add the code to:
- Add `django_resource` to `settings.py:INSTALLED_APPS`
- Add a `DJANGO_RESOURCE` settings object to `settings.py` with sane defaults
- Create a `resources` package within your main package
- Add a URL mount under `/resources` referencing the server

New blueprints will become available to generate spaces and resources.

#### Adding spaces

Generate a space, passing in a name:

``` bash
dj generate django_resource.space --name=v0
```

#### Adding resources

Generate a resource, passing in a space, name, and model

``` bash
    dj generate django_resource.resource --space=v0 --name=users --model=auth.User
```

#### Running the server

``` bash
    dj serve 9000
```

Visit "http://localhost:9000/resources"

### Using pip, pipenv, or poetry

#### Installation

``` bash
    pip install django_resource
    # ... or "poetry add django_resource"
    # ... or "pipenv add django_resource"
```

##### Add to INSTALLED APPS

Add `django_resource` to `INSTALLED_APPS` in `settings.py`:
``` python
    INSTALLED_APPS = [
        # ..,,
        'django_resource'
    ]
```

##### Add to settings

Create `DJANGO_RESOURCE` within `settings.py`:

``` python
    DJANGO_RESOURCE = {
    }
```

##### Add core packages

All resource definitions for a single server should be defined in one subpackage of your project folder.
The recommended package path is "yourapp.resources" if your app name is "yourapp".

- Create `yourapp/resources/__init__.py`
- Create `yourapp/resources/spaces/__init__.py`

##### Add server

Create `yourapp/resources/server.py`, the entrypoint to your resource server.

``` python
    from django_resource.server import Server

    server = Server()
```

##### Mount URL

In `yourapp/resources/urls.py` add the lines:

``` python
    from .server import server
    urlpatterns = server.urlpatterns
```

In your `urls.py`, add the lines:

``` python
    urlpatterns += [
        url(r'^resources', include('yourapp.resources.urls')
    ]
```

At this point, you no longer need to configure any further URLs using Django.

#### Adding spaces

##### V0

Create space "v0" referencing resource "clients" for storing client data:

- Create `yourapp/resources/spaces/__init__.py`
- Create `yourapp/resources/spaces/v0/__init__.py`
- Create `yourapp/resources/spaces/v0/space.py`:

``` python
    from django_resource.space import Space
    from .resources.users import users

    v0 = Space(name='v0')
    v0.add(clients)
```

Modify `youapp/resources/server.py` to import and include "v0":

``` python
    ...
    from .spaces.v0.space import v0

    ...
    server.add(v0)
```

##### V1

Create space "v1" referencing "users", a refactor of clients using the same underlying model:

Create `yourapp/resources/spaces/v1/space.py`:

``` python
    from django_resource.space import Space
    from .resources.users import users
    from .resources.groups import groups

    v1 = Space(name='v1')
    v1.add(users)
```

Modify `youapp/resources/server.py` to import and include "v1":

``` python
    ...
    from .spaces.v1.space import v1

    ...
    server.add(v1)
```

#### Adding resources

##### Clients

Create resource "clients" in space "v0":

Create `yourapp/resources/spaces/v0/resources/users.py`:

``` python
    from django_resource.resource import Resource

    clients = Resource(
        name='clients',
        model='yourapp.User'   # infer all fields from the model
        fields='*'             # since there is no groups resource,
                               # the "groups" relation will be rendered as an array of objects
    )
```

##### Users

Create resource "users" in space "v1":

Create `yourapp/resources/spaces/v1/resources/users.py`:

``` python
    from django_resource.resource import Resource
    from django_resource.types import Types

    def set_main_group(record, group_id):
        # remove and re-add to have the group return last
        record.groups.remove(group_id)
        record.groups.add(group_id)

    users = Resource(
        name='users',
        model='yourapp.User',
        fields={
            'id': 'id',                 # map individual fields to model fields
            'avatar': 'profile.avatar', # map through a has-one relationship
                                            # this field will be setable by default
                                            # if the field is set and profile does not exist,
                                            # a profile will be created and assigned to the user first
                                            # then the avatar field will be set
            'email': 'email_address',   # remap the name
            'role': {                   # redefine the field (recommended)
                # auto from model

                'source': 'role',           # the model source
                'description': 'role'       # description
                'type': "number",           # type of the field, including nullability
                'unique': False,            # uniqueness groups or true for self-only
                'index': ['role'],          # index groups or true for self-only
                'primary': False,           # primary key (default: false)
                'default': 2,               # default value
                'options': [{
                    "value": 1,
                    "label": "normal",
                }, {
                    "value": 2,
                    "label": "admin",
                    "can": {
                        "=set": "request.is_staff",
                    }
                },

                # manual: lazy loading

                "lazy": {                   # this field is lazy (default False)
                    "get.resource": True,   # in the list view only
                },

                # manual: access modifiers

                # these can be set to True, False, an access object, an access array, a Q object, or a lambda
                # the access object has role keys and True/False values
                # the access array is a list of access objects
                # the lambda takes the request and returns one of the simpler types
                "can": {
                    'get': [{"is_staff": True}, {"is_superuser": True}]      # this field can be viewed by staff or superusers (default True)
                    'set.initial': lambda r: Q(id=r.user.pk) | Q(is_staff=False)     # this field can be initialized set by the target user or if the target is not staff
                    'set': False,  # this field can not be changed after creation
                }
            },
            'groups': 'groups',         # this will either have type "[@groups" (array of link to group)
                                        # or "[{" (array of objects)
            'mainGroup': {                 # example of a link with custom getter/setter
                'type': "[@groups",
                'getter': 'groups.all.-1',    # read from a custom property on the model
                'needs': ['groups.*'],     # prefetch hinting for the custom property
                'setter': set_main_group   # write through a custom function
            },
        },
        can=[
            'get',
            'delete',
            'add.resource'
        ], # default methods: get, set, edit, add, delete, inspect
        features={
            'with': True,
            'where': True,
            'sort': True,
            'page': {
                'max_size': 20
            },
            'group': {
                'aggregators': [
                    'sum', 'count', 'max'
                ]
            },
            inspect: True,
            method: True
        },  # default features: where, with, sort, page, group, inspect, method
        access={
            'authenticated': {                  # for authenticated users
                'get.record': [{                     # allow GET /users/x/ 
                    '=id': 'me',                       # for x = current user ID
                }, {
                    '=record.email.not': 'record.username' # ... or any record where email != username
                }],
                'get.field': {                           # allow GET /users/x/*apps*
                    '=record.id': 'me',                     # for the current user 
                    'field.matches': '.*apps.*'             # and for any field containing "apps"
                }
            },
            'is_staff': {                       # for staff users
                'get': True,                        # allow GET /users/ and /users/x/y/
                'add': True,                        # allow POST /users/ and /users/x/y/
                'set.record': True,                 # allow PUT /users/x/
                'set.field': True,                  # allow PUT /users/x/y/
                'edit': True,                       # to PATCH /users/*/
                'delete.record': [{                      # to DELETE /users/x/
                    '=id': 'me',       # for x = current user
                }, {
                    'is_staff': False               # ... or any other non-staff user
                }]
            }
        },  # if given, enables access control on this resource
        aliases={
            'me': 'request.user.pk',
            'is_staff': 'request.user.is_staff',
            'authenticated': 'request.user.is_authenticated'
        }
    )
```

##### Groups

Create resource "groups" in space "v1"

Create `yourapp/spaces/v1/resources/groups.py`:

``` python
    from django_resource.resource import Resource

    groups = Resource(
        name='auth.Group',
        model='auth.Group',
        fields='*'
    )
```

#### Running the server

Run the usual dev server command in a virtual environment using virtualenv/activate, pipenv, or poetry:

``` bash
python manage.py runserver
```
