from .utils import cached_property
from .resource import Resource
from .schemas import ServerSchema
from .executor import SpaceExecutor, ServerExecutor, get_executor_class


class Server(Resource):
    class Schema(ServerSchema):
        pass

    def __init__(self, *args, **kwargs):
        super(Server, self).__init__(*args, **kwargs)
        self._setup = False

    def get_executor(self, query, prefix=None):
        state = query.state
        resource = state.get('resource')
        space = state.get('space')

        root = self
        if space:
            space = root = self.spaces_by_name[space]
        if resource:
            if not space:
                raise QueryExecutionError(
                    'query must have space if it has resource'
                )
            root = space.resources_by_name[resource]

        root_type = root.__class__.__name__.lower()
        if root_type == 'resource':
            cls = get_executor_class(root.engine)
            return cls()
        elif root_type == 'space':
            return SpaceExecutor()
        elif root_type == 'server':
            return ServerExecutor()
        else:
            raise ValueError(f'unexpected root type: {root_type}')

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
