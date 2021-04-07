"""Module containing Django meta helpers."""
from itertools import chain

from django.db.models import ManyToOneRel  # tested in 1.9
from django.db.models import OneToOneRel  # tested in 1.9
from django.db.models import (
    ForeignKey,
    ManyToManyField,
    ManyToManyRel,
    OneToOneField
)

from django.db.models.fields.related import (
    ForeignObjectRel as RelatedObject
)

def is_model_field(model, field_name):
    """Check whether a given field exists on a model.

    Arguments:
        model: a Django model
        field_name: the name of a field

    Returns:
        True if `field_name` exists on `model`, False otherwise.
    """
    try:
        get_model_field(model, field_name)
        return True
    except AttributeError:
        return False


def get_model_field(model, field_name):
    """Return a field given a model and field name.

    Arguments:
        model: a Django model
        field_name: the name of a field

    Returns:
        A Django field if `field_name` is a valid field for `model`,
            None otherwise.
    """
    meta = model._meta
    try:
        field = meta.get_field(field_name)
        return field
    except:
        related_objs = (
            f for f in meta.get_fields()
            if (f.one_to_many or f.one_to_one)
            and f.auto_created and not f.concrete
        )
        related_m2m_objs = (
            f for f in meta.get_fields(include_hidden=True)
            if f.many_to_many and f.auto_created
        )
        related_objects = {
            o.get_accessor_name(): o
            for o in chain(related_objs, related_m2m_objs)
        }
        if field_name in related_objects:
            return related_objects[field_name]


def get_model_field_and_type(model, field_name):
    field = get_model_field(model, field_name)

    if isinstance(field, RelatedObject):
        if isinstance(field.field, OneToOneField):
            return field, 'o2or'
        elif isinstance(field.field, ManyToManyField):
            return field, 'm2m'
        elif isinstance(field.field, ForeignKey):
            return field, 'm2o'
        else:
            raise RuntimeError("Unexpected field type")

    type_map = [
        (OneToOneField,  'o2o'),
        (OneToOneRel,  'o2or'),  # is subclass of m2o so check first
        (ManyToManyField,  'm2m'),
        (ManyToOneRel,  'm2o'),
        (ManyToManyRel, 'm2m'),
        (ForeignKey, 'fk'),  # check last
    ]
    for cls, type_str in type_map:
        if isinstance(field, cls):
            return field, type_str,

    return field, '',


def is_field_remote(model, field_name):
    """Check whether a given model field is a remote field.
    """
    if not hasattr(model, '_meta'):
        # ephemeral model with no metaclass
        return False

    model_field = get_model_field(model, field_name)
    return isinstance(model_field, (ManyToManyField, RelatedObject))


def get_related_model(field):
    return field.related_model


def get_reverse_m2m_field_name(m2m_field):
    return m2m_field.remote_field.name


def get_reverse_o2o_field_name(o2or_field):
    return o2or_field.remote_field.attname


def get_remote_model(field):
    return field.remote_field.model


def get_model_table(model):
    try:
        return model._meta.db_table
    except:
        return None

def has_limits(queryset):
    query = queryset.query
    return query.high_mark is not None or query.low_mark != 0

def get_limits(queryset):
    query = queryset.query
    return query.low_mark, query.high_mark

def clear_limits(queryset):
    query = queryset.query
    return query.clear_limits()
