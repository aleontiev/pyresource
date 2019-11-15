from django.utils.functional import cached_property
from .resource import Resource
from .version import version


class Server(Resource):
    _resource = {
        'name': 'server',
        'singleton': True,
        'description': 'server description',
        'space': '.'
    }
    _fields = {
        'version': {
            'type': 'string',
            'default': version
        },
        'url': 'string',
        'spaces': {
            'type': '[@spaces',
            'inverse': 'server',
            'default': []
        },
        'features': {
            'type': ['[string', '{'],
            'default': {
                'with': {
                    'max_depth': 5,
                },
                'where': {
                    'max_depth': 3,
                    'options': [
                        'is',
                        'not',
                        'in',
                        'not.in',
                        'lt',
                        'gte',
                        'gt',
                        'lte',
                        'range',
                        'null',
                        'not.null',
                        'contains',
                        'matches'
                    ]
                },
                'page': {
                    'max_size': 1000,
                    'size': 100
                },
                'group': {
                    'options': [
                        'max',
                        'min',
                        'sum',
                        'count',
                        'average',
                        'distinct',
                    ],
                },
                'sort': {
                }
            }
        },
        'types': {
            'type': '[@types',
            'default': []
        )
    }

    @cached_property
    def root(self):
        from .resource import Resource
        from .space import Space
        from .type import Type
        from .field import Field

        return Space(
            space='.',
            name='.',
            server=self,
            resources=[{
                Space.as_record(),
                Resource.as_record(),
                Type.as_record(),
                Field.as_record(),
                Type.as_record(),
                Server.as_record()
            }]
        )

    def setup(self):
        if not getattr(self, '_setup', False):
            self.spaces.add(self.root)
        self._setup = True

    @cached_property
    def urlpatterns(self):
        return self.get_urlpatterns()

    def get_urlpatterns(self):
        patterns = []
        self.setup()
        for space in self.spaces:
            patterns.extend(
                space.get_urlpatterns()
            )
        return patterns
