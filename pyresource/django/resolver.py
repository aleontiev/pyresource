from pyresource.exceptions import SchemaResolverError

from django.db import models
from django.db.models.fields import NOT_PROVIDED
from django.db.models.fields.related import ManyToManyRel, ManyToOneRel

from django.contrib.postgres import fields as postgres

from pyresource.resolver import SchemaResolver
from pyresource.utils import type_add_null


class DjangoSchemaResolver(SchemaResolver):
    # META_FIELDS: these fields can be inferred from Django models + field source
    META_FIELDS = {'type', 'default', 'choices', 'description', 'unique', 'primary', 'index'}

    def __init__(self, *args, **kwargs):
        self._models = {}

    def get_field_source_names(self, source):
        source = self.get_model(source)
        return [field.name for field in source._meta.get_fields()]

    def is_field_local(self, model, source):
        # may raise FieldDoesNotExist
        field = self.get_field(model, source)
        if isinstance(field, (
            ManyToManyRel,
            ManyToOneRel,
            ManyToManyField
        )):
            return False
        return True

    def get_default(self, source, field, space=None):
        model = self.get_model(source)
        try:
            field = self.get_field(model, field)
        except TypeError:
            return None

        default = getattr(field, 'default', None)
        if default == NOT_PROVIDED:
            default = None
        return default

    def get_type(self, source, field, space=None):
        model = self.get_model(source)
        field_name = field
        field = self.get_field(model, field_name)

        if isinstance(
            field, (
                models.DecimalField,
                models.FloatField,
                models.IntegerField
            )
        ):
            return type_add_null(field.null, 'number')
        elif isinstance(field, models.BooleanField):
            return 'boolean'
        elif isinstance(field, models.NullBooleanField):
            return ['null', 'boolean']
        elif isinstance(
            field, (
                models.DurationField,
                models.ImageField,
                models.CharField,
                models.TextField,
                models.UUIDField,
                models.GenericIPAddressField,
                models.DateTimeField,
                models.DateField,
                models.TimeField,
                models.FileField,
            )
        ):
            return type_add_null(field.null, 'string')
        elif isinstance(field, postgres.ArrayField):
            # TODO: infer nested field type
            return type_add_null(field.null, 'array')
        elif isinstance(field, postgres.JSONField) or (
            hasattr(models, 'JSONField') and isinstance(field, models.JSONField)
        ):  # Django 3.1 
            return type_add_null(field.null, ['object', 'array'])
        elif isinstance(
            field, (
                models.ForeignKey,
                models.OneToOneField,
                models.ManyToManyField,
                ManyToManyRel,
                ManyToOneRel
            )
        ):
            many = isinstance(field, (models.ManyToManyField, ManyToManyRel))
            if not space:
                raise SchemaResolverError(f'Could not determine type for {field_name}, space is unknown')
            related_model = field.related_model
            related = '.'.join((related_model._meta.app_label, related_model._meta.model_name))
            related = space.get_resource_for(related)
            type = f'@{related.name}' if related else self.get_pk_type(related_model)
            return {'type': 'array', 'items': type} if many else type

    def get_pk_type(self, model):
        pk_field = model._meta.pk
        if isinstance(pk_field, (models.TextField, models.UUIDField, models.CharField)):
            return 'string'
        else:
            # TODO: really?
            return 'number'

    def get_choices(self, source, field, space=None):
        model = self.get_model(source)
        try:
            field = self.get_field(model, field)
        except TypeError:
            return None

        choices = getattr(field, 'choices', None)
        if not choices:
            return None
        return choices

    def get_description(self, source, field, space=None):
        """Get field description"""
        model = self.get_model(source)
        try:
            field = self.get_field(model, field)
        except TypeError:
            return None

        try:
            doc = field.help_text
        except AttributeError:
            doc = None

        if not doc:
            doc = None
        return doc

    def get_unique(self, source, field, space=None):
        model = self.get_model(source)
        try:
            field = self.get_field(model, field)
        except TypeError:
            return False
        return getattr(field, 'unique', False)

    def get_primary(self, source, field, space=None):
        model = self.get_model(source)
        try:
            field = self.get_field(model, field)
        except TypeError:
            return False
        return getattr(field, 'primary_key', False)

    def get_index(self, source, field, space=None):
        model = self.get_model(source)
        try:
            field = self.get_field(model, field)
        except TypeError:
            return False
        return getattr(field, 'db_index', False)

    def get_field(self, model, field, space=None):
        if isinstance(field, dict) and field.get('queryset'):
            queryset = field['queryset']
            field = queryset.get('field')
        return model._meta.get_field(field)

    def get_model(self, source):
        if not source:
            raise SchemaResolverError('Invalid source (empty)')

        source = self.get_model_source(source)
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
            except Exception as e:
                raise SchemaResolverError(
                    f'Invalid source (not a registered model): {source}\n'
                    f'Error: {e}'
                )
        return models[source]


resolver = DjangoSchemaResolver()
