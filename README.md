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

Create `DJANGO_RESOURCE` and `BASE_URL` within `settings.py`:

``` python
    # in production, set this to the server hostname
    BASE_URL = os.environ.get('BASE_URL', 'localhost')
    DJANGO_RESOURCE = {
        'PAGE_SIZE': 100
    }
```

##### Add core packages

All resource definitions for a single server should be defined in one subpackage of your project folder.
The recommended package path is "app.resources" (if your app name is "app").

- Create `app/resources/__init__.py`
- Create `app/resources/spaces/__init__.py`

##### Add server

Create `app/resources/server.py`, the entrypoint to your resource server.

``` python
    from django_resource.server import Server

    server = Server(url=f'{settings.BASE_URL}/api')
```

##### Mount URL

In `app/resources/urls.py` add the lines:

``` python
    from .server import server
    urlpatterns = server.urlpatterns
```

In your `urls.py`, add the lines:

``` python
    urlpatterns += [
        url(r'^api', include('app.resources.urls'))
    ]
```

At this point, you no longer need to configure any further URLs using Django.

#### Add spaces

##### V0

Create space "v0":

- Create `app/resources/spaces/__init__.py`
- Create `app/resources/spaces/v0/__init__.py`
- Create `app/resources/spaces/v0/space.py`:

``` python
    from django_resource.space import Space
    from app.resources.server import server

    v0 = Space(name='v0', server=server)
```

##### V1

Create space "v1":

Create `app/resources/spaces/v1/space.py`:

``` python
    from django_resource.space import Space
    from app.resources.server import server

    v1 = Space(name='v1', server=server)
```

#### Adding resources

##### Clients

Create resource "clients" in space "v0":

- Create `app/resources/spaces/v0/resources/__init__.py`
- Create `app/resources/spaces/v0/resources/users.py`:

``` python
    from django_resource.resource import Resource
    from app.spaces.v0.space import v0

    clients = Resource(
        space=v0,
        name='clients',
        model='app.user'       # infer all fields from the model
        fields='*'             # since there is no groups resource,
                               # the "groups" relation will be rendered as an array of objects
    )
```

##### Users

Create resource "users" in space "v1":

Create `app/resources/spaces/v1/resources/users.py`:

``` python
    from django_resource.resource import Resource
    from django_resource.types import Types
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

##### Groups

Create resource "groups" in space "v1"

Create `app/spaces/v1/resources/groups.py`:

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
