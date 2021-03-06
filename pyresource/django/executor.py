try:
    from django.db.models import Prefetch, F, Value, OuterRef, Subquery
except ImportError:
    raise Exception('django must be installed')

import copy
from pyresource.executor import Executor
from pyresource.translator import ResourceTranslator
from pyresource.resolver import RequestResolver
from pyresource.exceptions import (
    Forbidden,
    FilterError,
    ResourceMisconfigured,
    SerializationError,
    SchemaResolverError,
    QueryValidationError,
    QueryExecutionError,
    NotFound,
    MethodNotAllowed,
)
from pyresource.utils.types import get_link
from django.contrib.postgres.aggregates import ArrayAgg
from pyresource.utils import resource_to_django, make_literal
from .operators import make_expression, make_filter
# use a single resolver across all executors
from .resolver import resolver
from .prefetch import FastQuery, FastPrefetch
from .utils import maybe_atomic, maybe_capture_queries
from pyresource.conf import settings


class DjangoQueryLogic:
    @classmethod
    def _get_sorts(cls, sorts, translate=None):
        if isinstance(sorts, str):
            sorts = [sorts]

        if not sorts:
            return None

        results = []
        for sort in sorts:
            desc = False
            if sort.startswith("-"):
                sort = sort[1:]
                desc = True
            if translate:
                sort = ResourceTranslator.translate(sort, translate)

            sort = resource_to_django(sort)
            if desc:
                # add descending sort marker
                sort = f'-{sort}'
            results.append(sort)
        return results

    @classmethod
    def _get_filters(cls, resource, where, query=None, request=None, translate=False):
        """Build `django.db.models.Q` object for a queryset

        For example:

        request.user.id = 123
        where = {
            "or": [
                {'=': ['.request.user.id', 'id']},
                {'>=': ['created', {'now': {}}]}
            ]
        }
        return = Q(id=123) | Q(created__gte=Now())
        """
        if not where:
            return None

        where = RequestResolver.resolve(where, query=query, request=request)
        try:
            return make_filter(where, translate=resource if translate else None)
        except FilterError as e:
            raise ResourceMisconfigured(
                f"{resource.id}: failed to build filters\n" f"Error: {e}"
            )

    @classmethod
    def _add_queryset_sorts(
        cls,
        resource,
        fields,
        queryset,
        query,
        request=None,
        level=None,
        related=None,
        **context,
    ):
        """Add .order_by"""
        source = cls._get_queryset_source(resource, related=related)
        sorts = None
        if isinstance(source, dict):
            qs = source.get("queryset")
            sort = qs.get("sort", None)
            sorts = cls._get_sorts(sort)

        state = cls._get_query_state(query, level=level)
        if state is True:
            state = {}

        sort = state.get("sort", None)
        if sort:
            sorts = cls._get_sorts(sort, translate=resource)

        # order by request sorts, or by default sorts
        if sorts:
            queryset = queryset.order_by(*sorts)
        return queryset

    @classmethod
    def _add_queryset_filters(
        cls,
        resource,
        fields,
        queryset,
        query,
        request=None,
        level=None,
        related=None,
        **context,
    ):
        """Add .filter"""
        source = cls._get_queryset_source(resource, related=related)
        can_filters = request_filters = default_filters = None
        if isinstance(source, dict):
            qs = source.get("queryset")
            where = qs.get("where", None)
            default_filters = cls._get_filters(
                resource, where, query=query, request=request
            )

        state = cls._get_query_state(query, level=level)
        if state is True:
            state = {}

        record_id = state.get("id", None)
        where = state.get("where", None)
        if where:
            request_filters = cls._get_filters(
                resource, where, query=query, request=request, translate=True
            )

        can = context.get('can')
        if isinstance(can, dict):
            can_filters = cls._get_filters(
                resource, can, query=query, request=request, translate=True
            )

        for filters in (can_filters, default_filters, request_filters):
            if filters:
                queryset = queryset.filter(filters)

        if record_id:
            queryset = queryset.filter(pk=record_id)

        return queryset

    @classmethod
    def _add_queryset_prefetches(
        cls,
        resource,
        fields,
        queryset,
        query,
        level=None,
        related=None,
        request=None,
        **context,
    ):
        """Add .prefetch_related to optimize deep query performance

        This indirectly supported nested filtering/ordering/pagination by recursively
        calling get_queryset to build the querysets at each query node.

        Prefetches are added for relation fields for which "take" is an object.
        This indicates that fields, not just values, should be included
        """
        state = cls._get_query_state(query, level=level)
        if state is True:
            return queryset

        prefetches = []
        take = state.get("take", {})
        root_field = query.state.get("field", None) if level is None else None
        take_root = root_field is not None and query.state.get("take") is not None
        if take or take_root:
            for field in fields:
                take_field = take.get(field.name)
                if take_root or (
                    take_field and (
                        isinstance(take_field, dict) or
                        (field.is_link and field.is_list)
                    )
                ):
                    # recursively build nested querysets
                    source = resolver.get_field_source(field.source)
                    source = resource_to_django(source)
                    related_resource = field.related
                    related_level = f"{level}.{field.name}" if level else field.name
                    # selection: which fields should be selected
                    related_fields = cls._take_fields(
                        related_resource,
                        action="get",
                        query=query,
                        request=request,
                        level=related_level,
                    )
                    # authorization: is the request allowed to prefetch this relation
                    related_can = cls._can(
                        related_resource,
                        'get.prefetch',
                        query=query,
                        request=request,
                        field=field
                    )
                    next_queryset = cls._get_queryset(
                        related_resource,
                        related_fields,
                        query,
                        request=request,
                        level=related_level,
                        can=related_can,
                        related=field
                    )
                    prefetches.append(
                        FastPrefetch(
                            source, queryset=next_queryset, to_attr=f".{field.name}"
                        )
                    )

        if prefetches:
            queryset = queryset.prefetch_related(*prefetches)
        return queryset

    @classmethod
    def _add_queryset_pagination(
        cls, resource, fields, queryset, query, count=None, level=None, **context,
    ):
        """Add pagination"""
        if isinstance(queryset, dict):
            # .aggregate was called, producing a dictionary result
            return queryset

        state = cls._get_query_state(query, level=level)
        if state is True:
            state = {}
        page = state.get("page", {})
        size = int(page.get("size", settings.PAGE_SIZE))
        after = page.get("after", None)
        offset = 0
        if level is not None:
            pass # return queryset  # TODO

        if after:
            try:
                after = cls._decode_cursor(after)
            except Exception as e:
                raise QueryValidationError(f"page:after is invalid: {after} ({str(e)})")

            if "offset" in after:
                # offset-pagination
                # after = {'offset': 100}
                offset = after["offset"]
                queryset = queryset[offset : offset + size + 1]
            elif "after" in after:
                # keyset-pagination
                # after = {'after': {'id': 1, 'name': 'test', ...}}
                # only ordered fields are included
                filters = {f"{key}__gt": value for key, value in after["after"].items()}
                queryset = queryset.filter(**filters)
            else:
                raise QueryValidationError("page:after is invalid: {after}")


        if count is not None:
            count["total"] = queryset.count()
        queryset = queryset[: size + 1]
        return queryset

    @classmethod
    def _make_aggregation(cls, aggregation):
        return make_expression(aggregation)

    @classmethod
    def _make_annotation(cls, field, **context):
        is_list = field.is_list
        source = resolver.get_field_source(field.source)
        if isinstance(source, str):
            # string annotation e.g. "user.name"
            source = resource_to_django(source)
            if is_list:
                kwargs = {}
                # TODO: refactor this to use the normal get_queryset logic
                # ArrayAgg does not work properly in prefetch querysets

                # optional ordering
                if isinstance(field.source, dict):
                    qs = field.source.get("queryset")
                    sort = qs.get("sort", None) if qs else None
                    if sort:
                        sort = f"{source}.{sort}"
                        kwargs["ordering"] = resource_to_django(sort)

                return ArrayAgg(source, **kwargs)
            else:
                return F(source)
        else:
            # functional annotation e.g. {"count": "location.users"}
            return make_expression(field.source)

    @classmethod
    def _add_queryset_fields(
        cls, resource, fields, queryset, query, level=None, **context,
    ):
        """Add fields

        All of a Resource's fields represented in a queryset ("resourced fields")
        are annotated with a prefix of "." in order to prevent
        naming conflicts between source and resourced fields
        """
        if isinstance(queryset, dict):
            return queryset

        annotations = {}
        state = cls._get_query_state(query, level=level)
        if state is True:
            # id only
            return queryset.only('pk')

        take = state.get("take", None)
        root_field = query.state.get("field", None) if level is None else None
        root_take = query.state.get("take", None)
        for field in fields:
            if root_field:
                if root_take:
                    # ignore field being prefetched
                    break
            else:
                if take and (
                    isinstance(take.get(field.name), dict) or
                    (field.is_link and field.is_list)
                ):
                    # ignore fields being prefetched
                    continue

            annotations[f".{field.name}"] = cls._make_annotation(field, **context)

        if annotations:
            queryset = queryset.annotate(**annotations)

        only = list(annotations.keys())
        only.append('pk')
        return queryset.only(*only)

    @classmethod
    def _add_queryset_distinct(
        cls, resource, fields, queryset, query, **context,
    ):
        """Add .distinct if the query has left/outer joins"""
        if isinstance(queryset, dict):
            # .aggregate was called, producing a dictionary result
            return queryset

        if context.get('related'):
            # handled separately
            return queryset

        has_joins = False
        for join in queryset.query.alias_map.values():
            if join.join_type: # and join.join_type != "INNER JOIN":
                has_joins = True
                break

        if has_joins:
            queryset = queryset.distinct()
        return queryset

    @classmethod
    def _add_queryset_aggregations(
        cls, resource, fields, queryset, query, **context,
    ):
        level = context.get('level', None)
        state = cls._get_query_state(query, level=level)
        if state is True:
            return queryset

        group = state.get('group')
        if not group:
            return queryset

        aggregations = {}
        for name, aggregation in group.items():
            # use .{name} for consistency with annotations/fields
            aggregations[f'.{name}'] = cls._make_aggregation(aggregation)

        result = queryset.aggregate(**aggregations)
        return result

    @classmethod
    def _get_queryset(
        cls, resource, fields, query, **context,
    ):
        queryset = cls._get_queryset_base(resource, **context)
        for add in (
            "prefetches",
            "filters",
            "sorts",
            "aggregations",
            "distinct",
            "pagination",
            "fields",
        ):
            queryset = getattr(cls, f"_add_queryset_{add}")(
                resource, fields, queryset, query, **context,
            )
        return queryset

    @classmethod
    def _get_queryset_source(self, resource, related=None):
        if related:
            # add context from related field
            related_source = related.source
            if isinstance(related_source, dict) and "queryset" in related_source:
                source = copy.deepcopy(resource.source) if isinstance(resource.source, dict) else {
                    'queryset': {
                        'model': resource.source
                    }
                }
                queryset = source['queryset']
                related_queryset = related_source['queryset']
                # add "where" from related_source
                if 'where' in related_queryset:
                    if 'where' not in queryset:
                        # use related queryset filter only
                        queryset['where'] = related_queryset['where']
                    elif queryset['where'] != related_queryset['where']:
                        # use related queryset filter and resource filter
                        queryset['where'] = {'and': [queryset['where'], related_queryset['where']]}
                    # otherwise, keep the same filter (it is the same)

                # add "sort" from related_source
                if 'sort' in related_queryset:
                    if 'sort' not in queryset:
                        queryset['sort'] = related_queryset['sort']
                    elif queryset['sort'] != related_queryset['sort']:
                        # overwrite the default sort order instead of concatenating sorts
                        # this is because a concatenated sort is rarely the intent
                        queryset['sort'] = related_queryset['sort']
            else:
                source = resource.source
        else:
            source = resource.source
        return source

    @classmethod
    def _get_queryset_base(cls, resource, related=None, **context):
        source = cls._get_queryset_source(resource, related=related)

        try:
            model = resolver.get_model(source)
        except SchemaResolverError as e:
            raise ResourceMisconfigured(
                f'{resource.id}: failed to resolve model from source "{source}"\n'
                f"Error: {e}"
            )

        queryset = model.objects.all()
        queryset = FastQuery(queryset)
        return queryset


class DjangoExecutor(Executor, DjangoQueryLogic):

    def _get_resource(
        self, endpoint, query, request=None, prefix=None, resource=None, queries=None, **context
    ):
        do_capture = isinstance(queries, dict)
        with maybe_capture_queries(capture=do_capture) as capture:
            resource = self._resource_from_query(query, resource)

            can = self._can(resource, f"get.{endpoint}", query, request)
            if not can:
                raise Forbidden()

            source = resource.source
            if endpoint == "resource":
                page_size = int(
                    query.state.get("page", {}).get("size", settings.PAGE_SIZE)
                )

            meta = {}

            fields = self._take_fields(
                resource, action="get", query=query, request=request,
            )

            if not source:
                # no source -> do not use queryset
                if not resource.singleton:
                    raise ResourceMisconfigured(
                        f'{resource.id}: cannot "get" a collection resource with no source'
                    )
                # singleton -> assume fields are all computed
                # e.g. user_id with source: ".request.user.id"
                data = self._serialize(
                    resource, fields, query=query, request=request, meta=meta, field_prefix='.'
                )
            else:
                if resource.singleton:
                    # get queryset and obtain first record
                    record = self._get_queryset(
                        resource, fields, query, request=request, can=can, **context
                    ).first()
                    if not record:
                        raise ResourceMisconfigured(
                            f"{resource.id}: could not locate record for singleton resource"
                        )
                    data = self._serialize(
                        resource,
                        fields,
                        query=query,
                        request=request,
                        record=record,
                        meta=meta,
                        field_prefix='.'
                    )
                else:
                    count = (
                        {} if endpoint == "resource" and settings.PAGE_TOTAL else None
                    )
                    queryset = self._get_queryset(
                        resource,
                        fields,
                        query,
                        count=count,
                        request=request,
                        can=can,
                        **context,
                    )
                    if isinstance(queryset, dict):
                        # aggregate data
                        # TODO: handle nested aggregates
                        records = queryset
                    elif endpoint == "resource":
                        # many records
                        records = list(queryset)
                        num_records = len(records)
                        if num_records and num_records > page_size:
                            link = self._get_next_page(query)
                            page_data = {"after": link}
                            if count:
                                page_data["total"] = count["total"]
                            if "page" not in meta:
                                meta["page"] = {}
                            page_key = "data" if prefix is None else f"data.{prefix}"
                            meta["page"][page_key] = page_data
                            records = records[:page_size]
                    else:
                        # one record only
                        records = queryset.first()
                        if not records:
                            # no record
                            raise NotFound()
                    data = self._serialize(
                        resource,
                        fields,
                        record=records,
                        query=query,
                        request=request,
                        meta=meta,
                        field_prefix='.'
                    )

            result = {"data": data}
            if meta:
                result["meta"] = meta
        if queries is not None:
            queries['queries'] = capture.queries
        return result

    def get_record(self, query, request=None, **context):
        return self._get_resource("record", query, request=request, **context)

    def get_field(self, query, request=None, **context):
        return self._get_resource("field", query, request=request, **context)

    def get_resource(self, query, request=None, **context):
        return self._get_resource("resource", query, request=request, **context)

    def explain_resource(self, query, request=None, resource=None, **context):
        resource = self._resource_from_query(query, resource)
        return {"data": {"resource": resource.serialize()}}

    def explain_record(self, query, **context):
        return self.explain_resource(query, **context)

    def explain_field(self, query, request=None, resource=None, **context):
        resource = self._resource_from_query(query, resource)
        field = query.state.get('field')
        field = resource.fields_by_name[field]
        return {"data": {"field": field.serialize()}}

    def add_resource(self, query, request=None, resource=None, **context):
        resource = self._resource_from_query(query, resource)

        if not self._can(resource, "add.resource", query, request):
            raise Forbidden()

        parameters = query.get('parameters', {})
        atomic = parameters.get('atomic', settings.ATOMIC)
        source = resource.source
        model = resolver.get_model(source)

        fields = self._take_fields(
            resource, action="add", query=query, request=request,
        )
        data = query.state.get("data")
        as_list = True
        if not isinstance(data, list):
            data = [data]
            as_list = False

        errors = {}
        with maybe_atomic(atomic):
            # build up instances
            instances = []
            for i, dat in enumerate(data):
                index = f'.{i}' if as_list else ''
                instance = model()
                ok = True
                for field in fields:
                    # 1. get value for field
                    if field.name in dat:
                        # use given value
                        value = dat[field.name]
                    else:
                        if field.default is not None:
                            # use default value
                            value = field.default
                        elif field.is_nullable:
                            # use null
                            value = None
                        else:
                            error = {
                                field.name: ["This field is required and cannot be null"]
                            }
                            if atomic:
                                raise BadRequest({f"data{index}": error})
                            else:
                                errors[f'data{index}'] = error
                                ok = False
                                break

                    # TODO: support related adds when objects are passed instead of IDs
                    # 2. validate value
                    try:
                        field.validate(field.type, value)
                    except Exception as e:
                        raise BadRequest(
                            f"{value} is invalid for field "
                            f"{field.id} with type {field.type}"
                        )

                    source = resolver.get_field_source(field.source)
                    if not source:
                        error = {
                            field.name: [
                                f"Cannot set field through one-way source function: {source}"
                            ]
                        }
                        if atomic:
                            raise BadRequest({f"data{index}": error})
                        else:
                            errors[f'data{index}'] = error
                            ok = False
                            break

                    if "." in source:
                        error = {
                            field.name: [f'Cannot add through nested source "{source}"']
                        }
                        if atomic:
                            raise BadRequest({f"data{index}": error})
                        else:
                            errors[f'data{index}'] = error
                            ok = False
                            break

                    if resolver.is_field_local(model, source):
                        # this is a "local" field that lives on the model itself
                        setattr(instance, source, value)
                    else:
                        # this is a "remote" field that is local to another model
                        # which means we cannot set the relationship until after creation
                        if not hasattr(instance, "_add_after"):
                            instance._add_after = {}
                        instance._add_after[field.name] = (field, value)
                if ok:
                    instances.append(instance)


            ids = []
            # actually save the instances and their new IDs
            for i, instance in enumerate(instances):
                index = f'.{i}' if as_list else ''
                try:
                    # save local fields
                    instance.save()
                    # save remote fields (to-many relationships)
                    if hasattr(instance, "_add_after"):
                        for field, value in instance._add_after.values():
                            source = resolver.get_field_source(field.source)
                            # TODO: what if this isnt a many-related-manager?
                            # is that possible for a remote field?
                            getattr(instance, source).set(value)
                        del instance._add_after
                    ids.append(instance.pk)
                except Exception as e:
                    error = {
                        field.name: [f'Failed to save record: {e}']
                    }
                    if atomic:
                        raise BadRequest({f"data{index}": error})
                    else:
                        errors[f'data{index}'] = error

            take = query.state.get("take", None)
            if take:
                # perform a get to return the created records
                query = query.action("get")
                if as_list:
                    query = query.where({"in": [resource.id_name, make_literal(ids)]})
                else:
                    query = query.id(ids[0])
                result = query.get(request=request, **context)
                return result
            else:
                # without take, return the number of rows modified
                result = {'data': len(ids)}
            if errors:
                result['errors'] = errors
            return result

    def add_field(self, query, request=None, **context):
        return

    def add_space(self, query, request=None, **context):
        return self._add_resources("space", query, request=request, **context)

    def add_server(self, query, request=None, **context):
        return self._add_resources("server", query, request=request, **context)

    def add_record(self, query, **context):
        raise MethodNotAllowed()
