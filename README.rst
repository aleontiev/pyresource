# django-resource

*django-resource* is an implementation of [Resource](https://resource.rest) for Django.

## Getting Started

### Using DJ

#### Installation

You can add this to your project with [DJ](https://djay.io)
DJ is a Django-specific development tool that wraps pyenv, virtualenv, pip, and pipenv/poetry.
It allows you to quickly add *django-resource* to your project and set up resources with the CLI.

.. code-block:: bash 
    dj add django-resource

This will run an initialization blueprint to automatically add the code to:
- Add `django_resource` to `settings.py:INSTALLED_APPS`
- Add `DJANGO_RESOURCE` settings object to `settings.py` with defaults
- Create `resources` package within your main package to contain all resource definitions
- Add a Resource server mounted under `/resources`

#### Adding resources

New blueprints will become available:

Generate one resource from a given model:
.. code-block:: bash
    dj generate django_resource.resource --space=v0 --name=users --model=auth.User

Generate resources from multiple models
.. code-block:: bash
    dj generate django_resource.resources --models=*

#### Running the server

.. code-block:: bash
    dj serve 9000

Visit "http://localhost:9000/resources"

### Using pip, poetry, 

#### Installation

.. code-block:: bash
    pip install django_resource
    # ... or "poetry add django_resource"
    # ... or "pipenv add django_resource"

#### Installed Apps

Add `django_resource` to `INSTALLED_APPS` in `settings.py`:
.. code-block:: python
    INSTALLED_APPS = [
        # ..,,
        'django_resource'
    ]

#### Settings

Create `DJANGO_RESOURCE` within `settings.py`:
.. code-block:: python
    DJANGO_RESOURCE = {
    }


#### Package

All resource definitions for a single server should be defined in one subpackage of your project folder.
The recommended package path is "yourapp.resources" (i.e. system path prefix `ROOT="yourapp/resources/"`)

- Create `$ROOT/__init__.py`
- Create `$ROOT/spaces/__init__.py`

#### Server

Create `server.py` with two spaces called "v0" and "v1":
.. code-block:: python
    from django_resource.server import Server
    from .spaces.v0.space import v0
    from .spaces.v1.space import v1

    server = Server()
    server.add(v0)
    server.add(v1)

#### Spaces

##### V0

Create space "v0" referencing resource "clients" for storing client data:

- Create `$ROOT/spaces/__init__.py`
- Create `$ROOT/spaces/v0/__init__.py`
- Create `$ROOT/spaces/v0/space.py`:
.. code-block:: python
    from django_resource.space import Space
    from .resources.users import users

    v0 = Space(name='v0')
    v0.add(clients)

##### V1

Create space "v1" referencing "users", a refactor of clients using the same underlying model:

Create `$ROOT/spaces/v1/space.py`:
.. code-block:: python
    from django_resource.space import Space
    from .resources.clients import clients

    v1 = Space(name='v1')
    v1.add(users)

#### Resources

##### Users

Create resource "clients" in space "v0":

Create `$ROOT/spaces/v0/resources/users.py`:
.. code-block:: python
    from django_resource.resource import Resource

    users = Resource(
        name='users',
        model='yourapp.User'   # infer all fields from the model
        fields='*'
    )

##### Clients

Create resource "users" in space "v1":

Create `$ROOT/spaces/v1/resources/users.py`
.. code-block:: python
    from django_resource.resource import Resource
    from django_resource.types import Types

    def get_best_group(record):
        return record.groups.all()[0]

    users = Resource(
        name='users',
        model='yourapp.User',
        fields={
            'id': 'id',                 # map individual fields to model fields
            'avatar': 'profile.avatar', # source through a relationship
            'email': 'email_address',   # remap field names, infer the rest
            'role': {                   # define field properties
                'source': 'role',       # ...but infer field type, choices through model
                'writable': False,
            },
            'groups': 'groups',         # this will either be a LinkMany (if groups is a resource)
            'bestGroup': {
                'type': Types.Link,
                'relation': 'groups',
                'get': get_best_group,
                'requires': ['groups.*'],
                'writable': False
            }
        },
        aliases={
            'me': 'request.user.pk'
        }
    )

#### URLs

In `yourapp/resources/urls.py` add the lines:
.. code-block:: python
    from yourapp.resources.server import server
    urlpatterns = server.urlpatterns

In your `urls.py`, add the lines:

.. code-block:: python
    urlpatterns += [
        url(r'^resources', include('yourapp.resources.urls')
    ]
