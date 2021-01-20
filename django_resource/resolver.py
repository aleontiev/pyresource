from .exceptions import SchemaResolverError


class SchemaResolver:
    def __init__(self, store):
        pass

    def get_model(self, source):
        raise NotImplementedError()

    META_FIELDS = {}

    @classmethod
    def get_model_name(cls, source):
        if isinstance(source, dict):
            queryset = source.get('queryset', {})
            model = queryset.get('model', None)
            if model:
                return model
            raise SchemaResolverError(f'Source has no model: {source}')
        return source

    def get_field_schema(self, source, field, space=None):
        source_model = SchemaResolver.get_model_name(source)
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

