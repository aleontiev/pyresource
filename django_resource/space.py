from .resource import Resource
from .typing import get_container, get_link


class Space(Resource):
    _schema = {
        'name': 'spaces'
        'description': 'spaces description'
        'space': '.',
        'singleton': False,
        'can': ['read', 'inspect']
        'parameters': None,
        'base': None,
        'features': None,
    }
    _fields = {
        'server': {
            'type': '@server',
            'inverse': 'spaces'
        },
        'name': 'string',
        'resources': {
            'type': '[@resources',
            'inverse': 'space'
        }
    }

    def __init__(self, **kwargs):
        if kwargs.get('space', None) == '.':
            # root space record uniquely uses itself
            # as the space
            kwargs['space'] = self
        return super(Space, self).__init__(**kwargs)

    @classmethod
    def get_urls(cls, self):
        pass

    @cached_property
    def resources_by_name(self):
        return {r.name: r for r in self.resources}

    def resolve(self, type, value):
        container, child = get_container(type)
        if container:
            if container == '{':
                value = {k:self.resolve(child, v) for k,v in value.items()}
            elif container == '[':
                value = [self.resolve(child, v) for v in value]
            elif container == '?':
                value = self.resolve(child, v)
        else:
            link, name = get_link(type)
            resource = self.resources_by_name[name]
            value = resource.get_record(value)

        return value
