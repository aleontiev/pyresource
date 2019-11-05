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
    from .resources.users import users
    from .resources.groups import groups

    v1 = Space(name='v1')
    v1.add(users)

#### Resources

##### Clients

Create resource "clients" in space "v0":

Create `$ROOT/spaces/v0/resources/users.py`:
.. code-block:: python
    from django_resource.resource import Resource

    clients = Resource(
        name='clients',
        model='yourapp.User'   # infer all fields from the model
        fields='*'             # since there is no groups resource,
                               # the "groups" relation will be rendered as Array of objects
    )

##### Users

Create resource "users" in space "v1":

Create `$ROOT/spaces/v1/resources/users.py`
.. code-block:: python
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
                'source': 'role',       # the model source
                'help': 'The user\'s role' # auto: help_text
                'type': Types.Integer,  # auto: type of the field
                'null': False,          # auto: nullable
                'unique': False,        # auto: unique
                'index': ['role'],      # auto: index
                'pk': False,            # auto: pk
                'default': 2,           # auto: default
                'options': [{           # auto: choices (by default all can be set)
                    "id": 1,
                    "text": "admin",
                    "$set": "staff"  #  only staff users can set this field to this value
                }], {
                    "id": 2,
                    "text": "normal",
                    "set": True         # everybody who can set this field can set the value to 2
                }],
                # manual: deferred
                "deferred": {           # this field is deferred (default False)
                    "list": True,           # in the list view only
                },
                # manual: access modifiers
                # these can be set to True, False, an access object, an access array, a Q object, or a lambda
                # the access object has role keys and True/False values
                # the access array is a list of access objects
                # the lambda takes the request and returns one of the simpler types
                'get': [{"is_staff": True}, {"is_superuser": True}]      # this field can be viewed by staff or superusers (default True)
                'set': lambda r: Q(id=r.user.pk) | Q(is_staff=False)     # this field can be set by the target user or if the target is not staff
                'edit': False,          # this field can be changed after creation (default True)
                'init': False           # this field cannot be set at initialization (default True)
            },
            'groups': 'groups',         # this will either be a Array(Link) (if groups is a resource)
                                        # or Array(Object)
            'mainGroup': {                 # example of a link with custom getter/setter
                'type': Types.Array[Types.Link],
                'link': 'groups',
                'getter': 'groups.all.-1',    # read from a custom property on the model
                'needs': ['groups.*'],     # prefetch hinting for the custom property
                'setter': set_main_group   # write through a custom function
            },
            'groupData': {
                'type': [Types.Link, Types.String],

        },  # taken as-is
        actions=Resource.changeActions({
            'delete': False,
            'add.*': True
        }),  # merged with default action set:
             # get, list, set, edit, add, delete, meta, get.*, add.*
        features=Resource.changeFeatures({
            'bulk': { # disable bulk set
                'set': False
            }
        }),  # merged with default features set:
             # filter, fields, sort, offset, limit, sum, count, max, avg
        access={
            'authenticated': {                  # for authenticated users
                'get': {                          # allow GET /users/x/
                    '$id': 'me'        # for x = current user ID
                }
            },
            'is_staff': {                       # for staff users
                'get.*': True,                    # allow GET /users/*/groups (see a user's groups)
                                                  # ...or GET /users/?fields.groups=*
                                                    # "users:get.groups" and "groups:get" are both required
                                                    # if one or both are filters, they are composed together
                'add.*': True,                    # allow POST /users/x/groups (add a group and attach to user 1)
                                                    # "users:create.groups" and "groups:create" are both required
                                                    # if one or both are filters, they are composed together
                                                    # request body must contain one group
                'get': True,                      # allow  GET /users/*/
                'add': True,                      # allow  POST /users/
                'set': True,                      # to PUT /users/*/
                'list': True,                     # to GET /users/
                'edit': True,                     # to PATCH /users/*/
                'delete': [{                      # to DELETE /users/x/
                    '$id': 'me',       # for x = current user
                }, {
                    'is_staff': False               # ... or any other non-staff user
                }]
            }
        },  # if given, enables access control on this resource
        aliases={
            'me': 'request.user.pk',
            'staff': 'request.user.is_staff' 
        }
    )

##### Groups

Create resource "groups" in space "v1"

Create `$ROOT/spaces/v1/resources/groups.py`
.. code-block:: python
    from django_resource.resource import Resource

    groups = Resource(
        name='auth.Group',
        model='auth.Group',
        fields='*'
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
