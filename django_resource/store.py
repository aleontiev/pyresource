from .utils import cached_property
from .query import Query

# META_FIELDS: these fields can be inferred from Django models + field source
META_FIELDS = {'type', 'default', 'choices', 'description', 'unique', 'index'}

class SchemaResolver(object):
    def get_field_schema(self, source, field, space=None):
        if isinstance(source, dict):
            schema = source
            source_model = source.get('source')
        else:
            schema = {'source': field}
            source_model = source

        model = self.get_model(source_model)

        if not model:
            # failed to resolve a model
            # TODO: throw exception?
            return schema

        for field in META_FIELDS:
            if field not in schema:
                # use getters to add metafields 
                # e.g. resolve "type" if not provided
                schema[field] = getattr(self, f'get_{field}')(source_model, field, space=space)

        return schema


def add_null(null, other):
    """Naybe add null to a JSONSChema type"""
    if not null:
        return other
    if isinstance(other, list):
        if 'null' not in other:
            other.append('null')
        return other
    elif isinstance(other, dict):
        return {'anyOf': [{'type': 'null'}, other]}
    elif isinstance(other, str):
        # string
        return ['null', other]
    else:
        raise ValueError(f'Bad type: {other}')


class DjangoSchemaResolver(SchemaResolver):

    def get_type(self, source, field, space=None):
        if isinstance(field, dict):
            raise AttributeError(f'cannot determine type from complex source: {source}')

        model = self.get_model(source)
        field_name = field
        field = self.get_field(model, field_name)
        from django.db import models
        from django.contrib.postgres import fields as postgres

        if isinstance(field, models.DecimalField):
            return add_null(field.null, 'number')
        elif isinstance(field, models.FloatField):
            return add_null(field.null, 'number')
        elif isinstance(field, models.PositiveIntegerField):
            return add_null(field.null, 'number')
        elif isinstance(field, models.IntegerField):
            return add_null(field.null, 'number')
        elif isinstance(field, models.BooleanField):
            return 'boolean'
        elif isinstance(field, models.NullBooleanField):
            return ['null', 'boolean']
        elif isinstance(field, models.DurationField):
            return add_null(field.null, 'string')
        elif isinstance(field, (models.FileField, models.ImageField)):
            return add_null(field.null, 'string')
        elif isinstance(field, models.CharField):
            return add_null(field.null, 'string')
        elif isinstance(field, models.TextField):
            return add_null(field.null, 'string')
        elif isinstance(field, models.GenericIPAddressField):
            return add_null(field.null, 'string')
        elif isinstance(field, postgres.ArrayField):
            # TODO: infer nested field type
            return add_null(field.null, 'array')
        elif isinstance(field, postgres.JSONField) or (
            hasattr(models, 'JSONField') and isinstance(field, models.JSONField)
        ):  # Django 3.1 
            return add_null(field.null, ['object', 'array'])
        elif isinstance(field, models.UUIDField):
            return add_null(field.null, 'string')
        elif isinstance(field, models.DateTimeField):
            return add_null(field.null, 'string')
        elif isinstance(field, models.DateField):
            return add_null(field.null, 'string')
        elif isinstance(field, models.TimeField):
            return add_null(field.null, 'string')
        elif isinstance(field, (models.ForeignKey, models.OneToOneField)):
            if not space:
                raise AttributeError(f'Could not determine type for {field_name}, space is unknown')

            related = space.get_resource_for(source)
            return add_null(field.null, f'@{related.name}')
        #elif isinstance(field, models.ManyToManyField):
        # TODO: support M2M
        #    pass

    def get_choices(self, model, field, space=None):
        model = self.get_model(source)
        pass

    def get_description(self, model, field, space=None):
        pass

    def get_unique(self, model, field, space=None):
        pass

    def get_index(self, model, field, space=None):
        pass

    def get_field(self, model, field, space=None):
        return model._meta.get_field(field)

    def get_model(self, source):
        if not source:
            raise AttributeError('Invalid source (empty)')

        if not hasattr(self, '_models'):
            # cache of model name -> model
            self._models = {}

        models = self._models

        if source not in models:
            # resolve model at this time if provided, throwing an error
            # if it does not exist or if Django is not imported
            from django.apps import apps

            try:
                app_label, model_name = source.split(".")
            except Exception:
                raise AttributeError(f'Invalid source (too many dots): {source}')

            try:
                models[source] = apps.get_model(app_label=app_label, model_name=model_name)
            except Exception:
                raise AttributeError('Invalid source (not a registered model)')

        return models[source]


class Executor(object):
    """Executes Query, returns dict response"""

    def get(self, query, request=None, **context):
        """
            Arguments:
                query: query dict
                request: request object
                context: extra context
        """
        pass


class DjangoExecutor(Executor):
    pass


class Store(object):
    def __init__(self, resource):
        if resource.__class__.__name__ == 'Space':
            self.space = resource
            self.resource = None
            self.server = resource.server
        elif resource.__class__.__name__ == 'Server':
            self.server = resource
            self.space = self.resource = None
        else:
            self.resource = resource
            self.space = resource.space
            self.server = self.space.server

    def get_executor(self):
        return DjangoExecutor()

    def get_resolver(self):
        return DjangoSchemaResolver()

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
        if self.resource:
            initial["resource"] = self.resource.name

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
