from django_resource.executor import Executor
from django_resource.resolver import RequestResolver
from django_resource.exceptions import (
    Forbidden,
    FilterError,
    ResourceMisconfigured,
    SerializationError,
)
from .filters import DjangoFilter
from django_resource.conf import settings


class DjangoExecutor(Executor):
    @classmethod
    def get_filters(cls, resource, where, query=None, request=None):
        """Build `django.db.models.Q` object for a queryset"""
        # e.g.
        # where = {"or": [{'=': ['.request.user.id', 'id']}, {'>=': ['created', {'now': {}}]}]
        # filters = Q(id=123) | Q(created__gte=Now())
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
    def add_queryset_sorts(cls, resource, queryset, query, request=None, **context):
        """Add .order_by"""
        return queryset

    @classmethod
    def add_queryset_filters(cls, resource, queryset, query, request=None, **context):
        """Add .filter"""
        return queryset

    @classmethod
    def add_queryset_prefetches(cls, resource, queryset, query, request=None, **context):
        """Add .prefetch_related"""
        return queryset

    @classmethod
    def add_queryset_annotations(cls, resource, queryset, query, request=None, **context):
        """Add .annotate"""
        return queryset

    @classmethod
    def add_queryset_aggregations(cls, resource, queryset, query, request=None, **context):
        """Add .aggregate"""
        return queryset

    @classmethod
    def add_queryset_pagination(cls, resource, queryset, query, request=None, **context):
        """Add limit/PK filter"""
        return queryset

    @classmethod
    def add_queryset_fields(cls, resource, queryset, query, request=None, **context):
        """Add .only/.defer"""
        return queryset

    @classmethod
    def add_queryset_distinct(cls, resource, queryset, query, request=None, **context):
        """Add .distinct if the query has left joins"""
        return queryset

    @classmethod
    def get_queryset(cls, resolver, resource, query, request=None, **context):
        queryset = cls.get_queryset_base(resolver, resource, query, request=request, **context)
        for add in (
            "sorts",
            "filters",
            "prefetches",
            "annotations",
            "aggregations",
            "pagination",
            "fields",
            "distinct",
        ):
            queryset = getattr(cls, f"add_queryset_{add}")(
                resource, queryset, query, request=request, **context
            )
        return queryset

    @classmethod
    def get_queryset_base(cls, resolver, resource, query, request=None, **context):
        source = resource.source
        if isinstance(source, dict):
            queryset = source.get('queryset')
            where = queryset.get("where", None)
            sort = queryset.get('sort', None)
            source = queryset.get("model", None)
            if not source:
                raise ResourceMisconfigured(
                    f"{resource.id}: no model in source: {source}"
                )
            filters = cls.get_filters(
                resource,
                where,
                query=query,
                request=request
            )
        else:
            filters = None

        try:
            model = resolver.get_model(source)
        except SchemaResolverError as e:
            raise ResourceMisconfigured(
                f'{resource.id}: failed to resolve model from source "{source}"\n'
                f"Error: {e}"
            )

        if filters:
            try:
                queryset = model.objects.filter(filters)
            except Exception as e:
                raise ResourceMisconfigured(f"{resource.id}: cannot apply base filters")
        else:
            queryset = model.objects.all()

        return queryset

    def get_resource(self, query, request=None, **context):
        resource = self.store.resource

        if not self.can(resource, "get.resource", query, request):
            raise Forbidden()

        source = resource.source
        page_size = query.state.get("page", {}).get("size", settings.DEFAULT_PAGE_SIZE)
        meta = {}

        if not source:
            # no source -> do not use queryset
            if not resource.singleton:
                raise ResourceMisconfigured(
                    f'{resource.id}: cannot execute "get" on a collection with no source'
                )
            # singleton -> assume fields are all computed
            # e.g. user_id with source: ".request.user.id"
            data = self.serialize(resource, query=query, request=request, meta=meta)
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
                    resource, query=query, request=request, record=record, meta=meta
                )
            else:
                queryset = self.get_queryset(resolver, resource, query, request=request, **context)
                records = list(queryset)
                num_records = len(records)
                if num_records > page_size:
                    # TODO: add pagination links to "meta"
                    records = records[:page_size]
                data = self.serialize(
                    resource, record=records, query=query, request=request, meta=meta
                )

        result = {"data": data}
        if meta:
            result["meta"] = meta
        return result

    def get_record(self, query, request=None, **context):
        resource = self.store.resource

        can = self.can(resource, "get.record", query=query, request=request)
        if not can:
            raise Forbidden()

        queryset = self.get_queryset(resource, query, request=request, can=can, **context)
        record = queryset.first()
        meta = {}
        data = self.serialize(
            resource, record=record, query=query, request=request, meta=meta
        )
        result = {"data": data}
        if meta:
            result["meta"] = meta
        return result

    def get_field(self, query, request=None, **context):
        resource = self.store.resource

        if not self.can(resource, "get.field", query, request):
            raise Forbidden()

        if query.state.get("take"):
            # use get_related to return related data
            # this requires "prefetch" permission on this field
            # or "get.prefetch" permission on the related field
            return self.get_related(query, request=request, **context)

        queryset = self.get_queryset(resource, query, request=request, **context)

    def get_related(self, query, request=None, **context):
        pass  # TODO
