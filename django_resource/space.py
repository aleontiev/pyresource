from .resource import Resource
from .utils import cached_property
from .types import get_link, get_type_name, get_type_names, get_type_property
from collections import defaultdict
from .resolver import SchemaResolver
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
                    "concat": [
                        "server.url",
                        "name",
                        "'/'"
                    ]
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
        self._by_source = None
        result = super(Space, self).__init__(**kwargs)
        # trigger a binding with server
        assert self.server != None
        return result

    @cached_property
    def by_source(self):
        if self._by_source is None:
            self._by_source = defaultdict(list)
            for resource in self.resources:
                if resource.source:
                    source = SchemaResolver.get_model_name(resource.source)
                    self._by_source[source].append(resource)
        return self._by_source

    @property
    def space(self):
        # return root space
        return self.server.root

    def get_resource_for(self, source):
        resources = self.by_source[source]
        len_resources = len(resources)
        if len_resources == 0:
            raise AttributeError(f'Space {self.name}: no resource for {source}')
        elif len_resources >= 2:
            # TODO: list all matches
            raise AttributeError(
                f'Could not determine resource for {source}, '
                f'found multiple possible matches: '
                f'{resources[0].name} and {resources[1].name}'
            )
        return resources[0]

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
                    space = self.server.spaces_by_name.get(key)
                    if not space:
                        raise Exception(f'Invalid spaces key: "{key}"')
                    return space
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
                if '.' in key:
                    try:
                        space_id, resource_name = key.split('.')
                    except Exception:
                        raise Exception(f'Invalid resources key: "{key}"')
                    space = self.resolve_record('spaces', space_id)
                    resource = space.resources_by_name.get(resource_name)
                    if not resource:
                        raise Exception(f'Invalid resources key: "{key}"')
                    return resource
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

    @cached_property
    def resources_by_name(self):
        result = {}
        for resource in self.resources:
            result[resource.name] = resource
        return result

    @cached_property
    def urls(self):
        return self.get_urls()

    def get_urls(self):
        patterns = []
        for resource in self.resources:
            patterns.extend(resource.urls)
        return patterns
