from .resource import Resource
from .types import get_container, get_link
from .utils import cached_property


class Space(Resource):
    class Schema:
        id = "spaces"
        name = "spaces"
        description = "spaces description"
        space = "."
        can = ["read", "inspect"]
        fields = {
            "server": {"type": "@server", "inverse": "spaces"},
            "name": {
                "type": "string",
                "primary": True
            },
            "resources": {
                "type": {"is": "array", "of": "@resources"},
                "inverse": "space",
                "default": []
            },
        }

    def __init__(self, **kwargs):
        if kwargs.get("space", None) == ".":
            # root space record uniquely references itself
            kwargs["space"] = self
        # records keyed by resource, for each of the resources in this space
        # for example, the root space (Space: .) will have records
        # ...for "spaces" (e.g. ".")
        # ...for "resources" (e.g. "resources", "spaces")
        # ...for "server" (e.g. "server")
        # ...for "types" (e.g. "any", "integer", "object")
        self._records = {}
        return super(Space, self).__init__(**kwargs)

    # e.g. "spaces" "."
    def resolve_record(self, name, key):
        if name not in self._records:
            records = self._records[name] = {}
            record = records.get(key, None)
            if not record:
                record = records[key] = 
            return record

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

            return self.resolve_record(name, value)
        return value
