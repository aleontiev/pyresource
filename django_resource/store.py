from .utils import cached_property
from .query import Query
from .exceptions import ResourceMisconfigured

# META_FIELDS: these fields can be inferred from Django models + field source
META_FIELDS = {'type', 'default', 'choices', 'description', 'unique', 'index'}

class SchemaResolver(object):
    def get_field_schema(self, source, field, space=None):
        if isinstance(source, dict):
            schema = source
            source_model = source.get('model')
        else:
            schema = {'source': field}
            source_model = source

        if not source_model:
            return field

        model = self.get_model(source_model)

        if not model:
            return field

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
            raise SchemaResolverError(f'cannot determine type from complex source: {source}')

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
                raise SchemaResolverError(f'Could not determine type for {field_name}, space is unknown')

            related = space.get_resource_for(source)
            return add_null(field.null, f'@{related.name}')
        elif isinstance(field, models.ManyToManyField):
            if not space:
                raise SchemaResolverError(f'Could not determine type for {field_name}, space is unknown')
            related = space.get_resource_for(source)
            return {'type': 'array', 'items': f'@{related.name}'}

    def get_choices(self, model, field, space=None):
        choices = field.choices
        if not choices:
            return None
        return choices

    def get_description(self, model, field, space=None):
        """Get field description"""
        doc = field.help_text
        if not doc:
            doc = str(field)
        return doc

    def get_unique(self, model, field, space=None):
        pass

    def get_index(self, model, field, space=None):
        pass

    def get_field(self, model, field, space=None):
        return model._meta.get_field(field)

    def get_model(self, source):
        if not source:
            raise SchemaResolverError('Invalid source (empty)')

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
                raise SchemaResolverError(f'Invalid source (too many dots): {source}')

            try:
                models[source] = apps.get_model(app_label=app_label, model_name=model_name)
            except Exception:
                raise SchemaResolverError(f'Invalid source (not a registered model): {source}')

        return models[source]


class Executor(object):
    """Executes Query, returns dict response"""
    def __init__(self, store, **context):
        self.store = store
        self.context = context

    def get(self, query, request=None, **context):
        raise NotImplementedError()


class DjangoExecutor(Executor):
    def get_filters(self, where, query, request):
        if not where:
            return None

        # build Q() object for queryset
        # e.g. 
        # where = {"or": [{'=': ['.request.user.id', 'id']}, {'>=': ['created', {'now': {}}]}]
        # filters = Q(id=123) | Q(created__gte=Now())
        pass

    def get_queryset(self, query, request=None, **context):
        resource = self.store.resource
        source = resource.source
        if isinstance(source, dict):
            where = source.get('where')
            source = source.get('model')
            if not model:
                raise ValueError('no model')
            filters = self.get_filters(where, query, request)
        else:
            filters = None

        try:
            model = self.store.resolver.get_model(source)
        except SchemaResolverError:
            raise ResourceMisconfigured(f'{resource.id}: cannot lookup model from {source}')

        if filters:
            try:
                queryset = model.objects.filter(filters)
            except Exception as e:
                raise ResourceMisconfigured(f'{resource.id}: cannot apply filters')
        else:
            queryset = model.objects.all()

        # TODO: ordering
        # TODO: filtering
        # TODO: pagination
        # TODO: annotations
        # TODO: aggregations
        return self.filter_queryset(queryset, query, request, **context)

    def filter_queryset(self, queryset, query, request, **context):
        pass

    def get(self, query, request=None, **context):
        """
            Arguments:
                query: query object
                request: request object
        """
        if query.state.get('field'):
            return self.get_field(query, request=request, **context)
        elif query.state.get('record'):
            return self.get_record(query, request=request, **context)
        elif query.state.get('resource'):
            return self.get_resource(query, request=request, **context)
        else:
            raise ValueError('space execution is not supported')

    def get_resource(self, query, request=None, **context):
        if not self.can('resource.get', query, request):
            raise Unauthorized()

        resource = self.store.resource
        source = resource.source
        if not source:
            # no source -> do not use queryset
            if not resource.singleton:
                raise ResourceMisconfigured(
                    f'{resource.id}: cannot execute "get" on a collection with no source'
                )
            # singleton -> assume fields are all computed
            # e.g. user_id with source: ".request.user.id"
            self.serialize(resource, query, request, meta=meta)
            return

        meta = {}
        if resource.singleton:
            # get queryset and obtain first record
            record = self.get_queryset(query, request=request, **context).first()
            if not record:
                raise ResourceMisconfigured(
                    f'{resource.id}: could not locate record for singleton resource'
                )
            data = self.serialize(resource, query, request, record=record, meta=meta)
        else:
            data = []
            queryset = self.get_queryset(query, request=request, **context)
            for record in queryset:
                data.append(self.serialize(resource, record, query, request, meta=meta))

        result = {'data': data}
        if meta:
            result['meta'] = meta
        return result

    def get_record(self, query, request=None, **context):
        can = self.can('get.record', query, request)
        if not can:
            raise Unauthorized()

        queryset = self.get_queryset(
            query,
            request=request,
            can=can,
            **context
        )
        record = queryset.first()
        meta = {}
        data = self.serialize(resource, record, query, request, meta=meta)
        result = {'data': data}
        if meta:
            result['meta'] = meta
        return result

    def get_field(self, query, request=None, **context):
        if not self.can('field.get', query, request):
            raise Unauthorized()

        if query.state.get('take'):
            # use get_related to return related data
            # this requires "prefetch" permission on this field 
            # or "get.prefetch" permission on the related field
            return self.get_related(query, request=request, **context)

        queryset = self.get_queryset(query, request=request, **context)

    def get_related(self, query, request=None, **context):
        pass  # TODO

    def serialize(self, resource, instance, query=None, request=None):
        pass

    def can(self, action, query, request):
        return True  # TODO



class Store(object):
    def __init__(self, resource):
        self.server = self.resource = self.space = None
        if resource.__class__.__name__ == 'Space':
            self.space = resource
        elif resource.__class__.__name__ == 'Resource':
            self.resource = resource

    def get_executor(self):
        return DjangoExecutor(self)

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
