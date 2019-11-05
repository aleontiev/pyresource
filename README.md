# django-resource

*django-resource* is an implementation of [Resource](https://resource.rest) for Django.

## Getting Started

### Using DJ

#### Installation

You can add this to your project with [DJ](https://djay.io)
DJ is a Django-specific development tool that wraps pyenv, virtualenv, pip, and pipenv/poetry.
It allows you to quickly add *django-resource* to your project and set up resources with the CLI.

``` bash 
    dj add django-resource
```

This will run an initialization blueprint to automatically add the code to:
- Add `django_resource` to `settings.py:INSTALLED_APPS`
- Add `DJANGO_RESOURCE` settings object to `settings.py` with defaults
- Create `resources` package within your main package to contain all resource definitions
- Add a Resource server mounted under `/resources`

#### Adding resources

New blueprints will become available:

Generate one resource from a given model:
```
    dj generate django_resource.resource --space=v0 --name=users --model=auth.User
```

Generate resources from multiple models
```
    dj generate django_resource.resources --models=*
```

#### Running the server

```
    dj serve 9000
```

Visit "http://localhost:9000/resources"

### Using pip, pipenv, or poetry

#### Installation

``` python
    pip install django_resource
    # ... or "poetry add django_resource"
    # ... or "pipenv add django_resource"
```

#### Installed Apps

Add `django_resource` to `INSTALLED_APPS` in `settings.py`:
``` python
    INSTALLED_APPS = [
        # ..,,
        'django_resource'
    ]
```

#### Settings

Create `DJANGO_RESOURCE` within `settings.py`:
``` python
    DJANGO_RESOURCE = {
    }
```

#### Package

All resource definitions for a single server should be defined in one subpackage of your project folder.
The recommended package path is "yourapp.resources" if your app name is "yourapp".

- Create `yourapp/resources/__init__.py`
- Create `yourapp/resources/spaces/__init__.py`

#### Server

Create `yourapp/resources/server.py` with two spaces called "v0" and "v1":
```
    from django_resource.server import Server
    from .spaces.v0.space import v0
    from .spaces.v1.space import v1

    server = Server()
    server.add(v0)
    server.add(v1)
```

#### Spaces

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

##### V1

Create space "v1" referencing "users", a refactor of clients using the same underlying model:

Create `yourapp/resources/spaces/v1/space.py`:
```
    from django_resource.space import Space
    from .resources.users import users
    from .resources.groups import groups

    v1 = Space(name='v1')
    v1.add(users)
```

#### Resources

##### Clients

Create resource "clients" in space "v0":

Create `yourapp/resources/spaces/v0/resources/users.py`:
```
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
                'type': "?number",          # type of the field
                'unique': False,            # uniqueness groups
                'index': ['role'],          # index groups
                'primary': False,           # primary key (default: false)
                'default': 2,               # default value
                'options': [{               # possible values
                    "id": 1,
                    "option": "admin",
                    "can": {
                        "=set": "is_staff",
                        "get": True
                    }                       # only staff users can set this field to this value
                }], {
                    "id": 2,
                    "option": "normal",
                    "can": {
                        "set": True,
                        "get": True
                    }                       # everybody can set this field
                }],

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
                    'set': lambda r: Q(id=r.user.pk) | Q(is_staff=False)     # this field can be set by the target user or if the target is not staff
                    'edit': False,  # this field can be changed after creation (default True)
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
        methods=[
            'delete',
            'add.resource'
        ], # default methods: get, set, edit, add, delete, inspect
        features={
            'with': True
            'where': True
            'sort': True
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
        }),  # default features: where, with, sort, page, group, inspect, method
        access={
            'authenticated': {                  # for authenticated users
                'get.record': {                          # allow GET /users/x/ 
                    '=id': 'me'        # for x = current user ID
                },
                'get.field': {                           # allow GET /users/x/apps_*
                    '=id': 'me',
                    '=field.startswith': 'apps'
                }
            },
            'is_staff': {                       # for staff users
                'get': True,                      # allow  GET /users/ and /users/id/field/
                'add': True,                      # allow  POST /users/
                'set': True,                      # to PUT /users/*/
                'edit': True,                     # to PATCH /users/*/
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

#### URLs

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
