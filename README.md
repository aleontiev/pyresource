# django-resource

**django-resource** is an implementation of [Resource](https://resource.rest) for Django.

Contents:
  * [Getting Started](#getting-started)
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
        url(r'^resources', include('yourapp.resources.urls'))
    ]
```

At this point, you no longer need to configure any further URLs using Django.

#### Add spaces

##### V0

Create space "v0":

- Create `yourapp/resources/spaces/__init__.py`
- Create `yourapp/resources/spaces/v0/__init__.py`
- Create `yourapp/resources/spaces/v0/space.py`:

``` python
    from django_resource.space import Space
    from yourapp.resources.server import server

    v0 = Space(name='v0', server=server)
```

##### V1

Create space "v1":

Create `yourapp/resources/spaces/v1/space.py`:

``` python
    from django_resource.space import Space
    from yourapp.resources.server import server

    v1 = Space(name='v1', server=server)
```

#### Adding resources

##### Clients

Create resource "clients" in space "v0":

Create `yourapp/resources/spaces/v0/resources/users.py`:

``` python
    from django_resource.resource import Resource
    from yourapp.spaces.v0.space import v0

    clients = Resource(
        space=v0,
        name='clients',
        model='yourapp.user'   # infer all fields from the model
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
    from yourapp.spaces.v1.space import v1

    users = Resource(
        name='users',
        model='yourapp.user',
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
                        "set": {"true": ".request.user.is_staff"},
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
                    'set': False,  # this field can not be changed after creation
                }
            },
            'groups': 'groups'
        },
        can={
            'get, delete, add.resource': True
        },
        features={
            'take': True,
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
            'explain': True,
            'action': True
        },  # default features: where, take, sort, page, group, explain, action
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
