from django_resource.executor import Executor
from django_resource.resolver import RequestResolver, SchemaResolver
from django_resource.exceptions import (
    Forbidden,
    FilterError,
    ResourceMisconfigured,
    SerializationError,
    QueryValidationError,
    QueryExecutionError,
    NotFound,
)
from .filters import DjangoFilter
from django_resource.conf import settings


class DjangoExecutor(Executor):
    @classmethod
    def get_sorts(cls, resource, sorts):
        if isinstance(sorts, str):
            sorts = [sorts]

        # TODO: add id sort if there is no sort
        # to enable keyset pagination
        if not sorts:
            return None
        return sorts

    @classmethod
    def get_filters(cls, resource, where, query=None, request=None):
        """Build `django.db.models.Q` object for a queryset

        For example:

        request.user.id = 123
        where = {
            "or": [
                {'=': ['.request.user.id', 'id']},
                {'>=': ['created', {'now': {}}
            ]
        }
        return = Q(id=123) | Q(created__gte=Now())
        """
        if not where:
            return None

        where = RequestResolver.resolve(where, query=query, request=request)
        filters = DjangoFilter(where)
        try:
            return filters.value
        except FilterError as e:
            raise ResourceMisconfigured(
                f"{resource.id}: failed to build filters\n" f"Error: {e}"
            )

    @classmethod
    def add_queryset_sorts(
        cls, resource, fields, queryset, query, request=None, level=None, **context,
    ):
        """Add .order_by"""
        source = resource.source
        sorts = None
        if isinstance(source, dict):
            qs = source.get("queryset")
            sort = qs.get("sort", None)
            sorts = cls.get_sorts(resource, sort)

        state = cls.get_query_state(query, level=level)
        sort = state.get("sort", None)
        if sort:
            sorts = cls.get_sorts(resource, sort)

        # order by request sorts, or by default sorts
        if sorts:
            queryset = queryset.order_by(*sorts)
        return queryset

    @classmethod
    def add_queryset_filters(
        cls, resource, fields, queryset, query, request=None, level=None, **context,
    ):
        """Add .filter"""
        source = resource.source
        request_filters = default_filters = None
        if isinstance(source, dict):
            qs = source.get("queryset")
            where = qs.get("where", None)
            default_filters = cls.get_filters(
                resource, where, query=query, request=request
            )

        state = cls.get_query_state(query, level=level)
        record_id = state.get("record", None)
        where = state.get("where", None)
        if where:
            request_filters = cls.get_filters(
                resource, where, query=query, request=request
            )

        if default_filters:
            queryset = queryset.filter(default_filters)

        if request_filters:
            queryset = queryset.filter(request_filters)

        if record_id:
            queryset = queryset.filter(pk=record_id)

        return queryset

    @classmethod
    def add_queryset_prefetches(
        cls, resource, fields, queryset, query, request=None, level=None, **context,
    ):
        """Add .prefetch_related"""
        # look for take.foo and translate into Prefetch(queryset=...)
        return queryset

    @classmethod
    def add_queryset_annotations(
        cls, resource, fields, queryset, query, request=None, level=None, **context,
    ):
        """Add .annotate"""
        return queryset

    @classmethod
    def add_queryset_pagination(
        cls,
        resource,
        fields,
        queryset,
        query,
        count=None,
        request=None,
        level=None,
        **context,
    ):
        """Add pagination"""
        state = cls.get_query_state(query, level=level)
        page = state.get("page", {})
        size = int(page.get("size", settings.DEFAULT_PAGE_SIZE))
        after = page.get("after", None)
        offset = 0
        if after:
            try:
                after = cls.decode_cursor(after)
            except Exception:
                raise QueryValidationError(f"page:after is invalid: {after}")

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
    def add_queryset_fields(
        cls, resource, fields, queryset, query, request=None, level=None, **context,
    ):
        """Add .only"""
        only = set()

        for field in fields:
            source = SchemaResolver.get_field_source(field.source)
            if source is None:
                # ignore fields without a source name i.e. real underlying field
                continue
            if "." in source:
                # for a nested source like a.b.c, return the first field: a
                source = source.split(".")[0]
            only.add(source)

        if only:
            only = list(only)
            queryset = queryset.only(*only)
        return queryset

    @classmethod
    def add_queryset_distinct(
        cls, resource, fields, queryset, query, level=None, request=None, **context,
    ):
        """Add .distinct if the query has left/outer joins"""
        has_joins = False
        for join in queryset.query.alias_map.values():
            if join.join_type and join.join_type != "INNER JOIN":
                has_joins = True
                break
        if has_joins:
            queryset = queryset.distinct()
        return queryset

    @classmethod
    def get_queryset(
        cls,
        resolver,
        resource,
        fields,
        query,
        request=None,
        count=None,
        level=None,
        **context,
    ):
        queryset = cls.get_queryset_base(resolver, resource)
        for add in (
            "filters",
            "sorts",
            "prefetches",
            "annotations",
            "fields",
            "distinct",
            "pagination",
        ):
            queryset = getattr(cls, f"add_queryset_{add}")(
                resource,
                fields,
                queryset,
                query,
                request=request,
                level=level,
                count=count,
                **context,
            )
        # print(str(queryset.query))
        return queryset

    @classmethod
    def get_queryset_base(cls, resolver, resource):
        source = resource.source
        try:
            model = resolver.get_model(source)
        except SchemaResolverError as e:
            raise ResourceMisconfigured(
                f'{resource.id}: failed to resolve model from source "{source}"\n'
                f"Error: {e}"
            )
        return model.objects.all()

    def get_resource(self, query, request=None, **context):
        return self._get("resource", query, request=request, **context)

    @classmethod
    def merge_meta(cls, meta, other, name):
        if not other:
            return
        meta.update(other)

    def get_server(self, query, request=None, prefix=None, **context):
        server = self.store.server
        spaces = server.spaces_by_name
        take = query.state.get("take")
        data = {}
        meta = {}
        for name, space in spaces.items():
            shallow = True
            if take is not None:
                if not take.get(name, False):
                    continue
                if isinstance(take[name], dict):
                    shallow = False
            if shallow:
                data[name] = f"./{name}/"
            else:
                subquery = query.get_subquery(level=name).space(name)
                subprefix = name if prefix is None else f"{prefix}.{name}"
                subdata = self.get_space(
                    subquery, space=space, request=request, prefix=subprefix, **context
                )
                # merge the data
                data[name] = subdata["data"]
                # merge the metadata if it exists
                self.merge_meta(meta, subdata.get("meta"), name)

        result = {"data": data}
        if meta:
            result["meta"] = meta
        return result

    def get_space(self, query, request=None, prefix=None, space=None, **context):
        if space is None:
            space = self.store.space

        resources = space.resources_by_name
        take = query.state.get("take")
        data = {}
        meta = {}
        for name, resource in resources.items():
            shallow = True
            if take is not None:
                if not take.get(name, False):
                    continue
                if isinstance(take[name], dict):
                    shallow = False
            if shallow:
                data[name] = f"./{name}/"
            else:
                subquery = query.get_subquery(level=name).resource(name)
                subprefix = name if prefix is None else f"{prefix}.{name}"
                subdata = self.get_resource(
                    subquery,
                    resource=resource,
                    request=request,
                    prefix=subprefix,
                    **context,
                )
                # merge the data
                data[name] = subdata["data"]
                # merge the metadata if it exists
                self.merge_meta(meta, subdata.get("meta"), name)

        result = {"data": data}
        if meta:
            result["meta"] = meta
        return result

    def _get(
        self, endpoint, query, request=None, prefix=None, resource=None, **context
    ):
        if resource is None:
            resource = self.store.resource

        if not self.can(resource, f"get.{endpoint}", query, request):
            raise Forbidden()

        source = resource.source
        if endpoint == "resource":
            page_size = int(
                query.state.get("page", {}).get("size", settings.DEFAULT_PAGE_SIZE)
            )

        meta = {}

        fields = self.select_fields(
            resource, action="get", query=query, request=request,
        )

        if not source:
            # no source -> do not use queryset
            if not resource.singleton:
                raise ResourceMisconfigured(
                    f'{resource.id}: cannot execute "get" on a collection with no source'
                )
            # singleton -> assume fields are all computed
            # e.g. user_id with source: ".request.user.id"
            data = self.serialize(
                resource, fields, query=query, request=request, meta=meta
            )
        else:
            resolver = self.store.resolver
            if resource.singleton:
                # get queryset and obtain first record
                record = self.get_queryset(
                    resolver, resource, query, request=request, **context
                ).first()
                if not record:
                    raise ResourceMisconfigured(
                        f"{resource.id}: could not locate record for singleton resource"
                    )
                data = self.serialize(
                    resource,
                    fields,
                    query=query,
                    request=request,
                    record=record,
                    meta=meta,
                )
            else:
                count = (
                    {} if endpoint == "resource" and settings.PAGINATION_TOTAL else None
                )
                queryset = self.get_queryset(
                    resolver,
                    resource,
                    fields,
                    query,
                    count=count,
                    request=request,
                    **context,
                )
                if endpoint == "resource":
                    # many records
                    records = list(queryset)
                    num_records = len(records)
                    if num_records and num_records > page_size:
                        cursor = self.get_next_page(query)
                        page_data = {"after": cursor}
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
                data = self.serialize(
                    resource,
                    fields,
                    record=records,
                    query=query,
                    request=request,
                    meta=meta,
                )

        result = {"data": data}
        if meta:
            result["meta"] = meta
        return result

    def get_record(self, query, request=None, **context):
        return self._get("record", query, request=request, **context)

    def get_field(self, query, request=None, **context):
        return self._get("field", query, request=request, **context)
