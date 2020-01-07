from django.utils.functional import cached_property
from .resource import Resource
from .version import version


class Server(Resource):
    class Schema:
        id = "server"
        name = "server"
        singleton = True
        space = "."
        description = "server description"
        fields = {
            "version": {"type": "string", "default": version},
            "url": {"type": "string", "primary": True},
            "spaces": {
                "type": {"is": "array", "of": "@spaces"},
                "inverse": "server",
                "default": [],
            },
            "features": {
                "type": {
                    "is": "union",
                    "of": [{"is": "array", "of": "string"}, "object"],
                },
                "default": {
                    "with": {"max_depth": 5},
                    "where": {
                        "max_depth": 3,
                        "options": [
                            "is",
                            "not",
                            "in",
                            "not.in",
                            "lt",
                            "gte",
                            "gt",
                            "lte",
                            "range",
                            "null",
                            "not.null",
                            "contains",
                            "matches",
                        ],
                    },
                    "page": {"max_size": 1000, "size": 100},
                    "group": {
                        "options": ["max", "min", "sum", "count", "average", "distinct"]
                    },
                    "sort": True,
                    "inspect": True,
                    "method": True,
                },
            },
            "types": {
                "type": {"is": "array", "of": "@types"},
                "default": [],
                "inverse": "server",
            },
        }

    def __init__(self, *args, **kwargs):
        super(Server, self).__init__(*args, **kwargs)
        self._setup = False

    @cached_property
    def root(self):
        from .space import Space

        return Space(
            space=".",
            name=".",
            server=self,
            resources=["spaces", "resources", "types", "fields", "server"],
        )

    def setup(self):
        from .types import Type

        if not self._setup:
            self.add(self.root, "spaces")
            self.add(
                [
                    "any",
                    "null",
                    "string",
                    "number",
                    "boolean",
                    "type",
                    "link",
                    "union",
                    "map",
                    "tuple",
                    "object",
                    "option",
                    "array",
                ],
                "types",
            )
        self._setup = True

    @cached_property
    def urlpatterns(self):
        return self.get_urlpatterns()

    def get_urlpatterns(self):
        patterns = []
        self.setup()
        for space in self.spaces:
            patterns.extend(space.get_urlpatterns())
        return patterns
