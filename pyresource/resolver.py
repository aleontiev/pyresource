from .exceptions import SchemaResolverError, RequestResolverError
from .utils import is_literal, get, unliteral
from .expression import execute, methods


def get_resolver(engine):
    if engine == 'django':
        from .django.resolver import resolver
        return resolver
    else:
        raise NotImplementedError()


class SchemaResolver:
    def get_model(self, source):
        raise NotImplementedError()

    META_FIELDS = {}

    @classmethod
    def get_field_source(self, source):
        if isinstance(source, str):
            return source
        if isinstance(source, dict) and 'queryset' in source:
            queryset = source['queryset']
            return queryset.get('field')
        return None

    @classmethod
    def get_model_source(cls, source):
        if isinstance(source, str):
            return source
        if isinstance(source, dict) and 'queryset' in source:
            queryset = source.get('queryset', {})
            return queryset.get('model')
        return None

    def get_field_schema(self, source, field, space=None):
        source_model = self.get_model_source(source)
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

        - Arguments like .request.user.pk or .query.action.
        will be set to actual values

        - If expression arguments end up entirely as constants
        and the expression can be interpretted in Python,
        the expression will be reduced into constants.
        """
        if isinstance(data, dict):
            result = {
                cls.resolve(key, **context): cls.resolve(value, **context)
                for key, value in data.items()
            }
            if len(result) == 1:
                # possible expression that we can evaluate
                key = next(iter(result))
                value = result[key]
                # resolve child arguments recursively
                if key in methods and is_literal(value):
                    value = unliteral(value)
                    try:
                        result, _ = execute({key: value}, context)
                    except Exception as e:
                        raise RequestResolverError(
                            f'Failed to resolve {data} executing {key}({value})'
                            f'{e.__class__.__name__}: {e}'
                        )
                    return result
            return result
        elif isinstance(data, list):
            return [cls.resolve(dat, **context) for dat in data]
        elif isinstance(data, str) and data.startswith('.'):
            data = data[1:]
            # by default, treat as a literal if this is a string
            as_literal = True
            if data.endswith('.'):
                # if ends with ".", do not treat as a literal
                as_literal = False
                data = data[:-1]

            data = get(data, context)
            if as_literal and isinstance(data, str):
                data = f'"{data}"'
            return data
        else:
            # pass through
            return data

