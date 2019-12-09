from .resource import Resource
from .types import get_container, get_link
from .utils import cached_property


class Space(Resource):
    class Schema:
        name = "spaces"
        description = "spaces description"
        space = "."
        singleton = False
        can = ["read", "inspect"]
        fields = {
            "server": {"type": "@server", "inverse": "spaces"},
            "name": "string",
            "resources": {
                "type": {"is": "array", "of": "@resources"},
                "inverse": "space",
            },
        }

    def __init__(self, **kwargs):
        if kwargs.get("space", None) == ".":
            # root space record uniquely references itself
            kwargs["space"] = self
        return super(Space, self).__init__(**kwargs)

    @classmethod
    def get_urls(cls, self):
        pass

    @cached_property
    def resources_by_name(self):
        return {r.name: r for r in self.resources}

    def resolve(self, T, value):
        container, child = get_container(T)
        if container:
            if container == "object":
                value = {k: self.resolve(child, v) for k, v in value.items()}
            elif container == "array":
                value = [self.resolve(child, v) for v in value]
            elif container == "option":
                value = self.resolve(child, value)
        else:
            link, name = get_link(T)
            if not link:
                raise ValueError(f"Failed to resolve: {T} is not a link type")
            resource = self.resources_by_name[name]
            value = resource.get_record(value)

        return value
