from dataclasses import dataclass
from typing import Any
from django.utils.functional import lazy
from .typing import Type, validate, is_link
from .store import InMemoryStore


@dataclass
class Property(object):
    parent: Schema
    name: str
    type: Type
    value: Any
    default: Any

    def __post_init(self):
        self.value = self.parent.get_option(
            self.name,
            self.default
        )
        validate(self.type, self.value)
        self._link = is_link(self.type)

    @classmethod
    def make(cls, *args, **kwargs):
        return lazy(
            lambda: cls(*args, **kwargs),
            cls
        )

    def get(self, resolve=True):
        if resolve and self._link:
            return self.link
        else:
            return self.value

    def get_link(self):
        return self.space.resolve(
            self.type,
            self.value
        )

    def set(self, value):
        self.value = value
        self.clear_cache()

    def clear_cache(self):
        self.__dict__.pop('link', None)

    def add(self, value, index=None):
        if not isinstance(self.value, str) and isinstance(self.value, list):
            self.value.append(value)
        elif index and isinstance(self.value, dict):
            self.value[index] = value
        elif self.value is not None:
            self.value += value

        self.clear_cache()

    @cached_property
    def space(self):
        return self.parent.space

    @cached_property
    def link(self):
        return self.get_link()


class Schema(object):
    _properties = None
    _options = None
    _fields = None

    def __init__(
        self,
        **options
    ):
        assert(getattr(self, '_fields', None) is not None)

        self._options = options
        self._properties = {}

    def __getattr__(self, key):
        return self.get_property(key).get()

    def __setattr__(self, key, value):
        prop = self.get_property(key)
        prop.set(value)

    def add(self, key, value):
        return self._get(key).add(value)

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
                    value = prop.get()
        return prop

    def get(self, key=None):
        return self._get(key).get(resolve=False)

    def get_option(self, key, default=None):
        return self._options.get(key, default=default)

    def get_property(self, key):
        if key not in self._fields:
            raise AttributeError(f'{key} is not a valid property')

        if key not in self._properties:
            schema = self._fields[key]
            if not isinstance(schema, dict):
                schema = {
                    'type': schema
                }
            self._properties[key] = Property.make(
                parent=self,
                name=key,
                **schema
            )
        return self._properties[key]

    @property
    def server(self):
        return self.get('space.server.')
