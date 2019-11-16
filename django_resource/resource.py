from .store import InMemoryStore


class Resource(object):
    _store = InMemoryStore
    _resource = {
        'id': 'resources',
        'name': 'resources',
        'description': 'resources description',
        'space': '.',
        'singleton': False,
        'can': ['read', 'inspect'],
        'parameters': None,
        'base': None,
        'features': None,
    }
    _fields = {
        'id': {
            'primary': True,
            'type': 'string',
            'default': lambda resource: f'{resource.space.name}.{resource.name}'
        },
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
    _properties = None
    _options = None

    def __init__(
        self,
        **options
    ):
        assert(getattr(self, '_fields', None) is not None)

        self._options = options
        self._properties = {}
        self._data = self._store(self)

    def __getattr__(self, key):
        return self.get_property(key).get_value()

    def __setattr__(self, key, value):
        prop = self.get_property(key)
        prop.set_value(value)

    def _get(self, key):
        keys = [k for k in key.split('.') if k] if key else []
        value = self
        last = len(keys)
        if not last:
            raise ValueError(f'{key} is not a valid property of {self.name}')
        for i, key in enumerate(keys):
            is_last = i == last
            if key:
                prop = value.get_property(key)
                if not is_last:
                    value = prop.get_value()
        return prop

    def add(self, key, value, index=None):
        return self._get(key).add_value(value, index=index)

    def get(self, key=None):
        return self._get(key).get_value(resolve=False, id=True)

    def get_option(self, key, default=None):
        if key in self._options:
            return self._options[key]
        else:
            if callable(default):
                default = default(self)
            return default

    def get_property(self, key):
        from .field import Field
        if key not in self._fields:
            raise AttributeError(f'{key} is not a valid property')

        if key not in self._properties:
            schema = self._fields[key]
            if not isinstance(schema, dict):
                schema = {
                    'type': schema
                }
            self._properties[key] = Field.make(
                resource=self,
                name=key,
                **schema
            )
        return self._properties[key]

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

    @cached_property
    def id_field(self):
        for name, field in self._fields.items():
            if isinstance(field, dict) and field.get('primary', False):
                return name
        raise ValueError('Resource {self.name} has no primary key')

    def get_id(self):
        return getattr(self, self.id_field)


def is_resource(x):
    return isinstance(x, Resource)
