"""Borrowed from dynamic-rest

Added support for nested-prefetch-limits via window functions
"""

from collections import defaultdict
import copy
import traceback

from django.db import models
from django.db.models import Prefetch, QuerySet, Window
from django.db.models.functions import RowNumber

from django_cte import With, CTEManager

from .meta import (
    has_limits,
    get_limits,
    set_limits,
    clear_limits,
    get_model_field_and_type,
    get_remote_model,
    get_reverse_m2m_field_name,
    get_reverse_o2o_field_name
)


def get_manager(self, model):
    if not hasattr(model, 'cte_objects'):
        manager = CTEManager()
        manager.contribute_to_class(model, 'cte_objects')
    return model.cte_objects

With.get_manager = get_manager


# dict/object
class Record(dict):
    def __init__(self, *args, **kwargs):
        self.pk_field = kwargs.pop('pk_field', 'id')
        return super(Record, self).__init__(*args)

    @property
    def pk(self):
        try:
            return self[self.pk_field]
        except KeyError:
            return self['pk']

    def _get(self, name):
        if '.' in name:
            parts = name.split('.')
            obj = self
            for part in parts:
                obj = obj[part]
            return obj
        elif name == '*':
            return self
        else:
            raise AttributeError(name)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            # fall back on slower logic.
            return self._get(name)

    def __setattr__(self, name, value):
        if name != 'pk_field' and name != 'pk':
            self[name] = value
        else:
            super(Record, self).__setattr__(name, value)


class List(list):
    # shim for related m2m record sets
    def all(self):
        return self


class FastPrefetch(object):
    def __init__(self, field, queryset=None, to_attr=None):
        if isinstance(queryset, models.Manager):
            queryset = queryset.all()
        if isinstance(queryset, QuerySet):
            queryset = FastQuery(queryset)

        assert (queryset is None or isinstance(queryset, FastQuery))

        self.field = field
        self.query = queryset
        self.to_attr = to_attr

    @classmethod
    def make_from_field(cls, model=None, field_name=None, field=None, to_attr=None):
        assert (model and field_name) or field, (
            'make_from_field required model+field_name or field'
        )

        # For nested prefetch, only handle first level.
        field_parts = field_name.split('__')
        field_name = field_parts[0]
        nested_prefetches = '__'.join(field_parts[1:])

        field, ftype = get_model_field_and_type(model, field_name)
        if not ftype:
            raise RuntimeError("%s is not prefetchable" % field_name)

        qs = get_remote_model(field).objects.all()

        field_name = field_name or field.name
        prefetch = cls(field_name, qs, to_attr=to_attr)

        # For nested prefetch, recursively pass down remainder
        if nested_prefetches:
            prefetch.query.prefetch_related(nested_prefetches)

        return prefetch

    @classmethod
    def make_from_prefetch(cls, prefetch, parent_model):
        assert isinstance(prefetch, Prefetch)
        to_attr = getattr(prefetch, 'to_attr', None)
        if isinstance(prefetch.queryset, FastQuery):
            return cls(
                prefetch.prefetch_through,
                prefetch.queryset,
                to_attr=to_attr
            )
        else:
            return cls.make_from_field(
                model=parent_model,
                field_name=prefetch.prefetch_through,
                to_attr=to_attr
            )


class FastQueryCompatMixin(object):
    """ Mixins for FastQuery to provide QuerySet-compatibility APIs.
    They basically just modify the underlying QuerySet object.
    Separated in a mixin so it's clearer which APIs are supported.
    """
    def _get_values(self, queryset):
        if self.fields:
            return queryset.values(*self.fields)
        else:
            return queryset.values()

    def prefetch_related(self, *args):
        try:
            for arg in args:
                if isinstance(arg, str):
                    arg = FastPrefetch.make_from_field(
                        model=self.model,
                        field_name=arg
                    )
                elif isinstance(arg, Prefetch):
                    arg = FastPrefetch.make_from_prefetch(arg, self.model)
                if not isinstance(arg, FastPrefetch):
                    raise Exception("Must be FastPrefetch object")

                if arg.field in self.prefetches:
                    raise Exception(
                        "Prefetch for field '%s' already exists."
                    )
                self.prefetches[arg.field] = arg
        except Exception as e:  # noqa
            traceback.print_exc()

        return self

    def only(self, *fields):
        self.fields = fields
        return self

    def exclude(self, *args, **kwargs):
        self.queryset = self.queryset.exclude(*args, **kwargs)
        return self

    def count(self):
        qs = self.queryset._clone()
        return qs.count()

    def extra(self, *args,  **kwargs):
        self.queryset = self.queryset.extra(*args, **kwargs)
        return self

    def filter(self, *args, **kwargs):
        self.queryset = self.queryset.filter(*args, **kwargs)
        return self

    def order_by(self, *ordering):
        self.queryset = self.queryset.order_by(*ordering)
        return self

    def distinct(self, *args, **kwargs):
        self.queryset = self.queryset.distinct(*args, **kwargs)
        return self

    def get(self, *args,  **kwargs):
        as_object = kwargs.pop('as_object', False)
        if as_object:
            # use Django logic (as_object=True)
            queryset = self._get_django_queryset()
            return queryset.get(*args, **kwargs)
        else:
            # use custom logic (default)
            queryset = self.queryset
            count = queryset.count()
            if count > 1:
                raise queryset.model.MultipleObjectsReturned()
            elif count == 0:
                raise queryset.model.DoesNotExist()
            data = self._get_values(queryset)[0]
            # merge the prefetches
            self.merge_prefetches([data])
            # return as Record
            return Record(data, pk_field=self.pk_field)

    def first(self, *args, **kwargs):
        as_object = kwargs.pop('as_object', False)
        if as_object:
            # use Django logic (as_object=True)
            queryset = self._get_django_queryset()
            return queryset.first()
        else:
            # use custom logic (default)
            queryset = self.queryset
            data = self._get_values(queryset)
            try:
                data = data[0]
            except Exception:
                # not found, return None
                return None
            else:
                # found, merge in the prefetches
                self.merge_prefetch([data])
                return Record(data, pk_field=self.pk_field)

    @property
    def query(self):
        return self.queryset.query

    def _clone(self):
        new = copy.copy(self)
        new.queryset = new.queryset._clone()
        return new

    def _get_django_queryset(self):
        """Return Django QuerySet with prefetches properly configured."""

        prefetches = []
        for field, fprefetch in self.prefetches.items():
            has_query = hasattr(fprefetch, 'query')
            qs = fprefetch.query.queryset if has_query else None
            to_attr = fprefetch.to_attr
            prefetches.append(
                Prefetch(field, queryset=qs, to_attr=to_attr)
            )

        queryset = self.queryset
        if prefetches:
            queryset = queryset.prefetch_related(*prefetches)

        return queryset

    def annotate(self, *args, **kwargs):
        self.queryset = self.queryset.annotate(*args, **kwargs)
        return self

    def aggregate(self, *args, **kwargs):
        # TODO: support deferred aggregation similar to deferred limits
        # this can be useful for nested prefetch cases
        return self.queryset.aggregate(*args, **kwargs)


class FastQuery(FastQueryCompatMixin, object):

    def __init__(self, queryset):
        if isinstance(queryset, models.Manager):
            queryset = queryset.all()
        self.queryset = queryset
        self.model = queryset.model
        self.prefetches = {}
        self.fields = None
        self.pk_field = queryset.model._meta.pk.attname
        self._data = None
        self._ids = None

    def execute(self):
        if self._data is not None:
            return self._data

        # TODO: check if queryset already has values() called
        qs = self.queryset._clone()
        # build queryset
        data = self._get_values(qs)
        # execute queryset
        data = list(data)

        self.merge_prefetch(data)
        self._data = List(
            map(lambda obj: Record(obj, pk_field=self.pk_field), data)
        )

        return self._data

    def __iter__(self):
        """Allow this to be cast to an iterable.
        Note: as with Django QuerySets, calling this will cause the
              query to execute.
        """
        return iter(self.execute())

    def __getitem__(self, k):
        """Support list index and slicing, similar to Django QuerySet."""

        if self._data is not None:
            # Query has already been executed. Extract from local cache.
            return self._data[k]

        # Query hasn't yet been executed. Update queryset.
        if isinstance(k, slice):
            if k.start is not None:
                start = int(k.start)
            else:
                start = None
            if k.stop is not None:
                stop = int(k.stop)
            else:
                stop = None
            if k.step:
                raise TypeError("Stepping not supported")

            set_limits(self.queryset, start, stop)
            # do not execute yet
            return self
        else:
            set_limits(self.queryset, k, k+1)
            return self.execute()

    def __len__(self):
        return len(self.execute())

    def get_ids(self, ids):
        self.queryset = self.queryset.filter(pk__in=ids)
        return self

    def merge_prefetch(self, data):

        model = self.queryset.model

        rel_func_map = {
            'fk': self.merge_fk,
            'o2o': self.merge_o2o,
            'o2or': self.merge_o2or,
            'm2m': self.merge_m2m,
            'm2o': self.merge_m2o,
        }

        for prefetch in self.prefetches.values():
            # TODO: here we assume we're dealing with Prefetch objects
            #       we could support field notation as well.
            field, rel_type = get_model_field_and_type(
                model, prefetch.field
            )
            if not rel_type:
                # Not a relational field... weird.
                # TODO: maybe raise?
                continue

            func = rel_func_map[rel_type]
            func(data, field, prefetch)

        return data

    def _make_id_map(self, items, pk_field='id'):
        result = {}
        for item in items:
            try:
                key = item[pk_field]
            except KeyError:
                key = item['pk']
            result[key] = item
        return result

    def _get_ids(self, data):
        if self._ids is None:
            pk_field = self.queryset.model._meta.pk.attname
            self._ids = {o.get(pk_field, o['pk']) for o in data}

        return self._ids

    def merge_fk(self, data, field, prefetch):
        # Strategy: pull out field_id values from each row, pass to
        #           prefetch queryset using `pk__in`.
        to_attr = getattr(prefetch, 'to_attr', None) or field.name

        id_field = field.attname
        ids = set([
            row[id_field] for row in data if id_field in row
        ])
        prefetched_data = prefetch.query.get_ids(ids).execute()
        id_map = self._make_id_map(prefetched_data)

        for row in data:
            row[to_attr] = id_map.get(row[id_field], None)

        return data

    def merge_o2o(self, data, field, prefetch):
        # Same as FK.
        return self.merge_fk(data, field, prefetch)

    def merge_o2or(self, data, field, prefetch, m2o_mode=False):
        # Strategy: get my IDs, filter remote model for rows pointing at
        #           my IDs.
        #           For m2o_mode, account for there many objects, while
        #           for o2or only support one reverse object.

        ids = self._get_ids(data)

        # If prefetching User.profile, construct filter like:
        #   Profile.objects.filter(user__in=<user_ids>)
        remote_field = get_reverse_o2o_field_name(field)
        remote_filter_key = '%s__in' % remote_field
        filter_args = {remote_filter_key: ids}

        # Fetch remote objects
        remote_objects = prefetch.query.filter(**filter_args).execute()
        id_map = self._make_id_map(data, pk_field=self.pk_field)

        to_attr = prefetch.to_attr or prefetch.field

        reverse_found = set()  # IDs of local objects that were reversed
        for remote_obj in remote_objects:
            # Pull out ref on remote object pointing at us, and
            # get local object. There *should* always be a matching
            # local object because the remote objects were filtered
            # for those that referenced the local IDs.
            reverse_ref = remote_obj[remote_field]
            local_obj = id_map[reverse_ref]

            if m2o_mode:
                # in many-to-one mode, this is a list
                if to_attr not in local_obj:
                    local_obj[to_attr] = List([])
                local_obj[to_attr].append(remote_obj)
            else:
                # in o2or mode, there can only be one
                local_obj[to_attr] = remote_obj

            reverse_found.add(reverse_ref)

        # Set value to None for objects that didn't have a matching prefetch
        not_found = ids - reverse_found
        for pk in not_found:
            id_map[pk][to_attr] = List([]) if m2o_mode else None

        return data

    def merge_m2m(self, data, field, prefetch):
        # Strategy: pull out all my IDs, do a reverse filter on remote object.
        # e.g.: If prefetching User.groups, do
        #       Groups.filter(users__in=<user_ids>)

        ids = self._get_ids(data)

        base_qs = prefetch.query.queryset  # base queryset on remote model
        remote_pk_field = base_qs.model._meta.pk.attname  # get pk field name
        reverse_field = get_reverse_m2m_field_name(field)

        if reverse_field is None:
            # Note: We can't just reuse self.queryset here because it's
            #       been sliced already.
            filters = {
                field.attname + '__isnull': False
            }
            qs = self.queryset.model.objects.filter(
                pk__in=ids, **filters
            )
            joins = list(qs.values_list(
                field.attname,
                self.pk_field
            ))
        else:
            # Get reverse mapping (for User.groups, get Group.users)
            # Note: `qs` already has base filter applied on remote model.
            filters = {
                f'{reverse_field}__in': ids
            }
            if has_limits(base_qs):
                # remove limits, then use CTE + RowNumber
                # to re-introduce them using window functions
                base_qs = base_qs._clone()
                low, high = get_limits(base_qs)
                clear_limits(base_qs)
                order_by = base_qs.query.order_by
                if not order_by:
                    # if there is no order, we need to use pk
                    order_by = ['pk']
                cte = With(
                    base_qs.annotate(**{
                        '..row': Window(
                            expression=RowNumber(),
                            partition_by=[reverse_field],
                            order_by=order_by
                        )
                    }).filter(**filters)
                )
                joins = cte.queryset().with_cte(cte).filter(
                    **{'..row__lte': high, '..row__gt': low}
                ).order_by(*order_by).distinct()
            else:
                # no limits, use simple filtering
                joins = base_qs.filter(**filters)

            joins = list(joins.values_list(remote_pk_field, reverse_field))

        # Fetch remote objects, as values.
        remote_ids = set([o[0] for o in joins])

        query = prefetch.query._clone()
        # remove limits to get IDs without extra filtering issues
        if has_limits(query.queryset):
            clear_limits(query.queryset)

        remote_objects = query.get_ids(remote_ids).execute()
        id_map = self._make_id_map(remote_objects, pk_field=remote_pk_field)

        # Create mapping of local ID -> remote objects
        to_attr = prefetch.to_attr or prefetch.field
        object_map = defaultdict(List)
        for remote_id, local_id in joins:
            if remote_id in id_map:
                object_map[local_id].append(id_map[remote_id])

        # Merge into working data set.
        for row in data:
            row[to_attr] = object_map[row.get(self.pk_field, row['pk'])]

        return data

    def merge_m2o(self, data, field, prefetch):
        # Same as o2or but allow for many reverse objects.
        return self.merge_o2or(data, field, prefetch, m2o_mode=True)
