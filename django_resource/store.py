from .utils import cached_property, get
from .query import Query
from .exceptions import ResourceMisconfigured


class SchemaResolver:
    def __init__(self, store):
        self.store = store

    def get_model(self, source):
        raise NotImplementedError()

    META_FIELDS = {}
    def get_field_schema(self, source, field, space=None):
        source_model = source.get('model') if isinstance(source, dict) else source
        if isinstance(field, dict):
            schema = field
        else:
            schema = {'source': field}

        if not source_model:
            return schema

        model = self.get_model(source_model)

        if not model:
            return schema

        field_name = schema['source']
        for f in self.META_FIELDS:
            if f not in schema:
                # use getters to add metafields 
                # e.g. resolve "type" if not provided
                schema[f] = getattr(self, f'get_{f}')(
                    source_model, field_name, space=space
                )

        return schema


class Executor:
    """Executes Query, returns dict response"""
    def __init__(self, store, **context):
        self.store = store
        self.context = context

    def get(self, query, request=None, **context):
        raise NotImplementedError()


class RequestResolver:
    @classmethod
    def resolve(cls, data, **context):
        """Return a resolved version of filter data

        Arguments like .request.user.pk or .query.action.
        will be set to actual values
        """
        if isinstance(data, dict):
            return {
                cls.resolve(key, **context): cls.resolve(value, **context)
                for key, value in data.items()
            }
        elif isinstance(data, list):
            return [cls.resolve(dat, **context) for dat in data]
        elif isinstance(data, str) and data.startswith('.'):
            data = data[1:]
            # by default, treat as a literal if this is a string
            literal = True
            if data.endswith('.'):
                # if ends with ".", do not treat as a literal
                literal = False
                data = data[:-1]

            data = get(data, context)
            if literal:
                data = f'"{data}"'
            return data
        else:
            # pass through
            return data

class Store:
    def __init__(self, resource):
        self.server = self.resource = self.space = None
        if resource.__class__.__name__ == 'Space':
            self.space = resource
        elif resource.__class__.__name__ == 'Resource':
            self.resource = resource

    def get_executor(self):
        raise NotImplementedError()

    def get_resolver(self):
        raise NotImplementedError()

    @cached_property
    def executor(self):
        return self.get_executor()

    @cached_property
    def resolver(self):
        return self.get_resolver()

    @property
    def query(self):
        return self.get_query()

    def get_query(self, querystring=None):
        initial = {}
        if self.space:
            initial['space'] = self.space.name
        elif self.resource:
            initial["resource"] = self.resource.name
            initial["space"] = self.resource.space.name

        executor = self.executor
        if querystring:
            return Query.from_querystring(
                querystring,
                state=initial,
                executor=executor
            )
        else:
            return Query(
                state=initial,
                executor=executor
            )
