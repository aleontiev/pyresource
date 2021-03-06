pyresource
==========

**pyresource** is a Python implementation of a
`resource <https://resource.rest>`__ API server. Currently, there is one
implemented resource engine: django (allowing for resources that bind to
Django models). A web engine is in development (allowing for resources
that bind to other resource APIs)

Contents: \* `Definitions <#definitions>`__ \* `Getting
Started <#getting-started>`__ \* `Installation <#installation-1>`__ \*
`Add settings <#add-settings>`__ \* `Add server <#add-server>`__ \*
`Mount server <#mount-server>`__ \* `Add spaces <#add-spaces-1>`__ \*
`V0 <#v0>`__ \* `V1 <#v1>`__ \* `Add resources <#add-resources-1>`__ \*
`Clients <#clients>`__ \* `Users <#users>`__ \* `Groups <#groups>`__ \*
`Running the server <#running-the-server-1>`__ \* `Web
requests <#web-requests-1>`__ \* `Python
requests <#python-requests-1>`__ \* `Authorization <#authorization-1>`__

Definitions
-----------

-  A **resource** is a complex API type, either a *singleton*
   (referencing one record) or a *collection* (referencing many records)
-  A resource is made up of many **fields**
-  Each resource belongs to a **space** (a namespace)
-  Resources can have **link**-type fields that reference other
   resources within the same space
-  Each space is hosted on a **server** which is exposed at a particular
   URL
-  Users interact with resources by sending **actions** to the server as
   HTTP requests
-  Each space, resource, and field belonging to a server (and the server
   itself) has a unique **endpoint** and URL
-  Resource constructs a **query** object for each request from the
   request path, querystring, and body
-  Certain querystring parameter groups called **features** are given
   special treatment

Getting Started
---------------

This guide walks through each step in creating a small set of resource
APIs, assuming you are starting with a Django project

Installation
~~~~~~~~~~~~

-  .. rubric:: Run the following:
      :name: run-the-following

   .. code:: bash

       pip install pyresource
       # ... or "poetry add pyresource"
       # ... or "pipenv add pyresource"

Add settings
^^^^^^^^^^^^

-  In your ``settings.py``, add ``BASE_URL`` and use
   ``pyresource.configure`` to configure global options:

.. code:: python

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

Add server
^^^^^^^^^^

-  Create ``app/resources/server.py``, the entrypoint to your resource
   server:

.. code:: python

        from django.conf import settings
        from pyresource.server import Server

        server = Server(url=f'{settings.BASE_URL}/api')

-  Touch ``app/resources/__init__.py``

**Note**: all resource definitions for a single server should be defined
in one subpackage of your project folder. The recommended package path
is "app.resources" (if your app name is "app").

Mount server
^^^^^^^^^^^^

-  In ``app/resources/urls.py`` add the lines:

.. code:: python

        from .server import server
        from pyresource.django.urls import get_urlpatterns
        urlpatterns = get_urlpatterns(server)

-  In your ``urls.py``, add the lines:

.. code:: python

        urlpatterns += [
            url(r'^api', include('app.resources.urls'))
        ]

**Note**: after this point, you no longer need to configure any
additional URLs using Django. New spaces/resources will automatically be
routed to by the server's internal routing.

Add spaces
~~~~~~~~~~

V0
^^

Create space "v0":

-  Create ``app/resources/spaces/v0/space.py``:

.. code:: python

        from pyresource.space import Space
        from app.resources.server import server

        v0 = Space(name='v0', server=server)

-  Touch ``app/resources/spaces/__init__.py``
-  Touch ``app/resources/spaces/v0/__init__.py``

V1
^^

-  Create ``app/resources/spaces/v1/space.py``:

.. code:: python

        from pyresource.space import Space
        from app.resources.server import server

        v1 = Space(name='v1', server=server)

-  Touch ``app/resources/spaces/v1/__init__.py``

Add resources
~~~~~~~~~~~~~

Clients
^^^^^^^

-  Create ``app/resources/spaces/v0/resources/clients.py``:

.. code:: python

        from pyresource.resource import Resource
        from app.spaces.v0.space import v0

        clients = Resource(
            space=v0,
            name='clients',
            model='app.user'       # infer all fields from the model
            fields='*'             # since there is no groups resource,
                                   # the "groups" relation will be rendered as an array of objects
        )

-  Touch ``app/resources/spaces/v0/resources/__init__.py``

Users
^^^^^

-  Create ``app/resources/spaces/v1/resources/users.py``:

.. code:: python

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
                'inspect': {
                    '
                },
                'action': True
            }
        )

-  Touch ``app/resources/spaces/v1/resources/__init__.py``

Groups
^^^^^^

Create resource "groups" in space "v1"

Create ``app/spaces/v1/resources/groups.py``:

.. code:: python

        from pyresource.resource import Resource

        groups = Resource(
            name='auth.Group',
            model='auth.Group',
            fields='*'
        )

Running the server
~~~~~~~~~~~~~~~~~~

-  Run the usual Django development server command in a virtual
   environment (or use ``pipenv run`` or ``poetry run``)

.. code:: bash

        python manage.py runserver

Web requests
~~~~~~~~~~~~

Each of the default actions is conveniently mapped to one of the HTTP
verbs, but it is always possible to override the action by using the
``action`` feature. The following default actions can be made against
any endpoint (server, space, resource, field), provided the request has
access:

get
^^^

HTTP method: GET

get.server
''''''''''

Read data from the server endpoint through one or more of its spaces.
Example:

::

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

get.space
'''''''''

Read data from the space endpoint through one or more of its resources.
Example:

::

    -->
        GET /api/v1/?take.users=*&take.groups=*

    <-- 200
        {
            "data": {
                "users": [...],
                "groups": [...]
            }
        }

get.resource
''''''''''''

Read data from the resource endpoint through one or more of its fields.
Example:

::

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

get.field
'''''''''

Read data from the field endpoint. Example:

::

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

explain
^^^^^^^

HTTP method: OPTIONS

add
^^^

HTTP method: POST

set
^^^

HTTP method: PUT

edit
^^^^

HTTP method: PATCH

delete
^^^^^^

HTTP method: DELETE

Python requests
~~~~~~~~~~~~~~~

It is also possible to use the Python API to issue requests directly
from Python code. For example, to get data from the server endpoint:

.. code:: python

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

Or to get data from a specific resource:

.. code:: python

        # ...
        users = server.spaces_by_name['v0'].resources_by_name['users']
        print(users.query.get(request=request))

Authentication
~~~~~~~~~~~~~~

Resource is authentication-agnostic and can work with any authentication
provider/middleware. Authentication is not checked explicitly, but may
be required indirectly during authorization checks.

Authorization
~~~~~~~~~~~~~

Resource uses a flexible access control model that supports both open
and closed permissioning styles and is based on a single resource
attribute called ``can``: - If a resource does not specify the ``can``
attribute, all actions will be allowed for all requests (open
permissions, the default behavior) - If a resource does specify the
``can`` attribute, then: - ``can`` must be an object with action-keys
and expression-values - actions against this resource will only be
allowed if the expression-value for a matching action-key evaluates to
True or to an expression (closed permissions) - if an expression-value
evaluates to an expression (rather than a boolean), that expression is
applied as a query-filter to the resource (partial access controlled by
filters) - Fields and field options can also define ``can`` in a similar
fashion (field-specific permissions)

Expressions
~~~~~~~~~~~

Many resource and field attributes support expressions that can be used
to further refine resource declarations, such as: - ``resource.can`` -
``resource.before`` - ``resource.after`` - ``resource.source`` -
``field.default`` - ``field.source`` - ``field.can``

Expressions follow these principles: - All JSON values are considered
valid expressions - Any expression is either a literal, an identifier,
or an operator - A literal expression is either a boolean, a number, a
list, a string that starts and ends with " (double-quote), a dictionary
with more than one key, or the empty dictionary - An identifier
expression is a string that is not a literal string - An operator
expression is a dictionary with a single key (the operator name) and
value either: - a list of expressions (list argument style), or - a
dictionary of expressions (keyword argument style), or - a single
literal or identifier expression (single argument style)

Resource supports many built-in operators:

Control flow
^^^^^^^^^^^^

-  looping with ``each``:

   .. code:: json

       {
       "each": {
           "from": "users",
           "as": "user",
           "do": {
               "custom.notify": {
                   "email": "user.email",
                   "body": "'test'"
               }
           }
       }
       }

-  branching with ``case``:

   .. code:: json

       {
       "case": [{
           "if": [
               {">": ["date", {"today": {}}]},
               "'later'"
           ]
       }, {
           "if": {
               {"<": ["date": {"today": {}}]},
               "'earlier'"
       }, {
           "else": "'today'"
       }]
       }

-  aliasing with ``with``:

   .. code:: json

       {
       "with": {
           "aliases": [{
               "name": {
                   "join":  ["first_name", "' '", "last_name"]
               }
           }],
           "expression": {
               "format": "Hello {.name}, welcome to the server"
           }
       ]
       }

-  layering with ``coalesce``:

   .. code:: json

       {
       "coalesce": ["users.name", "users.first_name", "'Unknown'"]
       }

Arithmetic operations
^^^^^^^^^^^^^^^^^^^^^

-  list/string/object concatenation/append/merge: ``+``
-  object removal by key/list removal by value: ``-``
-  numeric binary: ``-``, ``+``, ``/``, ``*``, ``mod``, ``power``,
   ``round``
-  numeric unary: ``abs``, ``ceil``, ``floor``, ``sin``, ``cos``,
   ``tan``, ``asin``, ``acos``, ``atan``
-  numeric generators: ``pi``, ``e``
-  numeric variadic: ``max``, ``min``, ``avg``, ``deviation``

Logic operations
^^^^^^^^^^^^^^^^

-  unary negation:

   .. code:: json

       {
       "not": {"true": ".request.user.is_superuser"}
       }

-  unary predicates:

   .. code:: json

       {
       "true, false, null, empty": ".request.user.is_superuser"
       }

-  comparison:

   .. code:: json

       {
       "=, >, <=, >=, =, !=": ["id", 1]
       }

List operations
^^^^^^^^^^^^^^^

-  list reductions: ``contains``, ``any``, ``all``, ``index``,
   ``count``, ``reduce``, ``join``

   .. code:: json

       [{
       "index, count, contains": ["users.name", "'John'"]
       }, {
       "any, all": {
           "from": "users",
           "as": "user",
           "where": {"null": ".user"}
       }
       },
       {
       "reduce": {
           "from": "users",
           "as": "user",
           "accumulator": "names",
           "initial": [],
           "reducer": {"+": [".names", ".user"]}
       }
       }]

-  list manipulations: ``distinct``, ``filter``, ``bucket``, ``map``,
   ``key``, ``sort``, ``slice``, ``reverse``, ``max``, ``min``:

   .. code:: json

       [{
       "filter": {
           "from": "users",
           "as": "user",
           "where": {"null": ".user"}
       }
       },
       {
       "map": {
           "from": "users",
           "as": "user",
           "map": ".user.name"
       }
       },
       {
       "key": {
           "from": "users",
           "as": "user",
           "by": ".user.id"
       }
       },
       {
       "bucket": {
           "from": "users",
           "as": "user",
           "by": ".user.location"
       }
       },
       {
       "sort": {
           "from": "users",
           "as": "user",
           "by": {
               "lower": ".user.name"
           }
       }
       },
       {
       "slice": ["users", [1, -1]]
       },
       {
       "max, min, distinct, reverse": "users"
       }]

String operations
^^^^^^^^^^^^^^^^^

-  string manipulations: ``format``, ``replace``, ``slice``, ``trim``,
   ``upper``, ``lower``, ``title``, ``split``, ``reverse``:

   .. code:: json

       [
       {
       "format": "Hello {name}"
       },
       {
       "replace": {
           "from": "user.name",
           "replace": "'M.'",
           "with": "user.prefix"
       }
       },
       {
       "slice": ["user.name", [1, -1]]
       },
       {
       "split": ["user.name", "' '"]
       },
       {
       "reverse, lower, title, upper, trim": "user.name"
       }]

-  string reductions: ``contains``, ``index``, ``count`` (same interface
   as with lists; the string is treated like a character-list as in
   Python)

Object operations
^^^^^^^^^^^^^^^^^

-  object manipulations: ``keys``, ``values``, ``items``

   .. code:: json

       {
       "keys, values, items": "map"
       }

Date/time operations
^^^^^^^^^^^^^^^^^^^^

.. code:: json

    [
    {
        "today, now": []
    },
    {
        "delta": ["user.created", {"now": []}]
    }
    ]

Manual escaping
^^^^^^^^^^^^^^^

-  evaluating as a literal

   .. code:: json

       {
       "literal": "user"
       }

-  evaluating as an identifier

   .. code:: json

       {
       "identifier": "user"
       }

Custom operations
^^^^^^^^^^^^^^^^^

You can also customize Resource by adding your own operators.

The only requirements are: - an operator name - whether or not the
operator can take arguments as a single value, as a list, and/or as a
dict (any one, two, or all three) - a Python method or import string
referencing a function (ideally free of any side effects for performance
reasons)

Hooks
~~~~~

Resource provides two properties that support customizing the behavior
around built-in actions: - ``before`` is run before the given action(s)
- ``after`` is run after the given action(s)
