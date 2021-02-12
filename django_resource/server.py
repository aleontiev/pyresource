from .utils import cached_property
from .resource import Resource
from .schemas import ServerSchema


class Server(Resource):
    class Schema(ServerSchema):
        pass

    def __init__(self, *args, **kwargs):
        super(Server, self).__init__(*args, **kwargs)
        self._setup = False

    @cached_property
    def spaces_by_name(self):
        result = {}
        for space in self.spaces:
            result[space.name] = space
        return result

    @cached_property
    def root(self):
        from .space import Space

        return Space(
            space=".",
            name=".",
            server=self,
            engine="resource",
            resources=[
                "spaces",
                "resources",
                "types",
                "fields",
                "server"
            ],
        )

    def get_resource_by_id(self, id):
        return self.root.resolve_record('resources', id)

    def setup(self):
        if not self._setup:
            self.add("spaces", self.root)
            self.add("types", [
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
            ])
        self._setup = True

    @cached_property
    def urls(self):
        return self.get_urls()

    def get_urls(self):
        patterns = []
        self.setup()
        for space in self.spaces:
            patterns.extend(space.urls)
        return patterns
