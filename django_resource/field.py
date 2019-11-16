from dataclasses import dataclass
from django.utils.functional import lazy
from .typing import Type, validate, is_link, is_list
from .resource import Resource, is_resource

class Field(Resource):
    _meta = {
        'name': 'fields',
        'description': 'fields description',
        'singleton': False,
    }
    _fields = {
        'resource': {
            'type': '@resource',
            'inverse': 'fields'
        },
        'id': {
            'type': 'string',
            'default': lambda field: f'{field.resource.id}.{field.name}'
            'primary': True
        },
        'name': {
            'type': 'string'
        },
        'type': {
            'type': 'type'
        }
    }

    def __post_init(self):
        self._is_link = is_link(self.type)
        self._is_list = is_list(self.type)
        self.set_value(
            self.resource.get_option(
                self.name,
                self.default
            )
        )

    @classmethod
    def make(cls, *args, **kwargs):
        return lazy(
            lambda: cls(*args, **kwargs),
            cls
        )

    def get_value(self, resolve=True, id=False):
        if resolve and self._is_link:
            link = self.link
            return link.get_id() if id else link
        else:
            return self.value

    def get_link(self, link):
        return self.space.resolve(
            self.type,
            link
        )

    def set_value(self, value):
        validate(self.type, value)
        if self._is_link:
            if (
                is_resource(value) or (
                    isinstance(value, list) and
                    any((is_resource(v) for v in value))
                )
            ):
                # resource given -> resolve all links now to get IDs
                # usually this will not require any premature fetching
                # unless a mix of IDs and resources is given
                link = self.get_link(value)
                value = [
                    v.get_id() for v in link
                ] if self._is_list else link.get_id()

                self.value = value
                self.__dict__['link'] = link
            else:
                # id or ids given -> resolve links later
                self.value = value
                self.__dict__.pop('link', None)
        else:
            # simple assignment without links
            self.value = value

    def add_value(self, new_value, index=None):
        if self._is_list:
            value = self.value
            link = None

            if value is None:
                value = self.value = []

            if not isinstance(new_value, list):
                new_value = [new_value]

            ids = None
            link = None
            if self._is_link:
                link = self.link
                ids = set([v.get_id() for v in link])

            for v in new_value:
                if self._is_link:
                    # check ids before adding
                    id = v.get_id()
                    if id not in ids:
                        value.append(ids)
                        link.append(v)
                else:
                    # add directly
                    value.append(v)
        else:
            # cannot add on a non-list
            # TODO: support this for strings, objects, numbers
            raise NotImplementedError()

    @cached_property
    def space(self):
        return self.resource.space

    @cached_property
    def link(self):
        return self.get_link(self.value)
