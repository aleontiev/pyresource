from .store import InMemoryStore
from .features import default_features
from .methods import default_methods
from .schema import Schema, Property


class Resource(Schema):
    _resource = {
        'name': 'resources'
        'description': 'resources description'
        'space': '.',
        'singleton': False,
        'can': ['read', 'inspect']
        'parameters': None,
        'base': None,
        'features': None,
    }
    _fields = {
        'name': 'string',
        'singleton': 'boolean',
        'description': 'string',
        'space': '@space',
        'fields': {
            'type': '[@fields',
            'inverse': 'resource',
            'default': []
        },
        'can': ['null', '{', '['],
        'parameters': '?{',
        'base': '?@resources',
        'features': '?{',
        'abstract': {
            'type': 'boolean',
            'default': False
        }
    }
    def __init__(self, *args, **kwargs):
        super(Resource, self).__init__(*args, **kwargs)
        self._data = self._store(self)

    def get_record(self, key=None):
        if isinstance(key, Resource):
            return key
        return self._data.get(key)

    @classmethod
    def as_record(cls):
        name = cls._meta.get('name')
        return Resource(
            fields=['{}.{}'.format(name, key) for key in cls._fields.keys()],
            **cls._resource
        )

