from .resource import Resource
from .types import get_link, get_type_name, get_type_names


class Space(Resource):
    class Schema:
        id = "spaces"
        name = "spaces"
        description = "spaces description"
        space = "."
        can = ["read", "inspect"]
        fields = {
            "server": {
                "type": "@server",
                "inverse": "spaces"
            },
            "url": {
                "type": "string",
                "source": {
                    "join": {
                        "separator": "/",
                        "values": ["server.url", "name"]
                    }
                },
                "can": {"set": False}
            },
            "name": {
                "type": "string",
                "primary": True
            },
            "resources": {
                "type": {
                    "type": "array",
                    "items": "@resources"
                },
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

    def resolve_record(self, name, key):
        from .types import Type
        from .field import Field

        if self.name == '.':
            if name == 'server':
                return self.server
            if name == 'spaces':
                if key == self.name:
                    return self
                else:
                    raise Exception(f'Invalid {name} key: {key}')
            if name == 'resources':
                if key == 'server':
                    return self.server.as_record(space=self)
                if key == 'spaces':
                    return Space.as_record(space=self)
                if key == 'fields':
                    return Field.as_record(space=self)
                if key == 'types':
                    return Type.as_record(space=self)
                if key == 'resources':
                    return Resource.as_record(space=self)
                raise Exception(f'Invalid {name} key: {key}')
            if name == 'types':
                return Type.get_base_type(
                    key,
                    server=self.server
                )
            if name == 'fields':
                parts = key.split('.')
                resource_id = '.'.join(parts[0:-1])
                field_name = parts[-1]
                # todo: get field schema
                return Field(
                    id=key,
                    parent=self,
                    name=field_name,
                    resource=resource_id,
                )
            raise Exception(f'Invalid resource: {name}')

    # e.g. "spaces" "."
    def resolve_link(self, name, key):
        records = self._records.get(name)
        if not records:
            records = self._records[name] = {}

        record = records.get(key, None)
        if not record:
            record = records[key] = self.resolve_record(name, key)
        return record

    def resolve(self, T, value):
        name = get_type_name(T)
        names = get_type_names(T)
        if name:
            if name == 'object':
                child = get_type_property(T, 'additionalProperties')

                value = {k: self.resolve(child, v) for k, v in value.items()}
            elif name == 'array':

                value = [self.resolve(child, v) for v in value]
            elif name == "link":
                link = get_link(T)
                if not link:
                    raise ValueError(f"Failed to resolve: {T} not of link type")
                return self.resolve_link(link, value)
        if names:
            if len(names) == 2 and "null" in names:
                value = next(iter(set(names) - {"null"}))
                if value is None:
                    return None
                value = self.resolve(child, value)
            # TODO: support resolving more complex types
        return value

    def get_urlpatterns(self):
        patterns = []
        for resource in self.resources:
            patterns.extend(resource.get_urlpatterns())
        return patterns
