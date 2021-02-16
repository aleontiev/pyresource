from .resolver import SchemaResolver
from .exceptions import QueryValidationError
from .utils import is_literal


class ResourceTranslator:
    @classmethod
    def translate(cls, value, resource):
        """Translate value from resource-names to source-names

        Arguments:
            value: a string or container
            resource: starting resource
        """
        if isinstance(value, (list, tuple)):
            return [cls.translate(v, resource) for v in value]
        if isinstance(value, dict):
            return {k: cls.translate(v, resource) for k, v in value.items()}
        if value is None or isinstance(value, (bool, int, float)):
            # literal non-striong value
            return value
        if not value or is_literal(value):
            # empty string or literal value
            return value
        parts = value.split('.')
        # try to resolve it
        first = parts[0]
        field = resource.fields_by_name[first]
        source = SchemaResolver.get_field_source(field.source)
        if not source:
            if len(parts) == 1:
                # special-case for any resource field references without a "."
                # and without a direct source
                # -> we use the queryset annotations which are named .field
                # this assumes that the annotations must be included in the query
                # TODO: ensure that the annotations are included if used in a filter
                return f'.{value}'
            else:
                raise QueryValidationError(
                    f'cannot translate {value} from complex source {field.source}'
                )

        if len(parts) == 1:
            # no remainder, just return this
            return source

        related = field.related
        if not related:
            raise QueryValidationError(
                f'cannot translate {value}: field {first} has no related field'
            )
        remainder = cls.translate('.'.join(parts[1:]), field.related)
        return f'{source}.{remainder}'
