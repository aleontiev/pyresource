from .resource import Resource
from .types import get_link, get_type_name, get_type_names
from decimal import Decimal


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
                        "items": [
                            "server.url",
                            "name"
                        ]
                    },
                    "separator": "/"
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
    def resolve_link(self, name, key, throw=True):
        records = self._records.get(name)
        if not records:
            records = self._records[name] = {}

        record = records.get(key, None)
        if not record:
            try:
                record = records[key] = self.resolve_record(name, key)
            except Exception:
                if throw:
                    raise
                else:
                    # silently return None
                    return None
        return record

    def resolve(self, T, value, throw=True):
        name = get_type_name(T)
        names = get_type_names(T)
        if name:
            if name == 'object':
                properties = get_type_property(T, 'properties')
                additional = get_type_property(T, 'additionalProperties')
                if not isinstance(value, dict):
                    if throw:
                        raise ValueError(f'Failed to resolve: {value} not an object')
                    return value
                value = {
                    k: self.resolve(
                        additional if k not in properties else properties[k], v, throw=throw
                    ) for k, v in value.items()
                }
            elif name == 'array':
                if not isinstance(value, list):
                    if throw:
                        raise ValueError(f'Failed to resolve: {value} not an object')
                    return value
                items = get_type_property(T, 'items')
                if items:
                    value = [self.resolve(items, v, throw=throw) for v in value]
            elif name.startswith('@'):
                link = get_link(name)
                return self.resolve_link(link, value, throw=throw)
            elif name == 'null':
                if value is not None:
                    if throw:
                        raise ValueError(f'Failed to resolve: {value} is not null')
                    return value
            elif name == 'boolean':
                if not isinstance(value, bool):
                    if throw:
                        raise ValueError(f'Failed to resolve: {value} not a boolean')
                    return value
            elif name == 'number':
                if not isinstance(value, (int, float, Decimal)):
                    if throw:
                        raise ValueError(f'Failed to resolve: {value} not a number')
                    return value
        if names:
            for name in names:
                try:
                    val = self.resolve(name, value, throw=True)
                except ValueError:
                    # does not match this schema
                    continue
                else:
                    # matched this schema
                    return val
            if throw:
                raise ValueError(
                    f'Failed to resolve: {value} does not match any of {names}'
                )
        return value

    def get_urlpatterns(self):
        patterns = []
        for resource in self.resources:
            patterns.extend(resource.get_urlpatterns())
        return patterns
