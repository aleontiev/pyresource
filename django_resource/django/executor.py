from django_resource.store import Executor, RequestResolver
from django_resource.exceptions import Forbidden


class DjangoExecutor(Executor):
    def get_filters(self, resource, where, query, request):
        """Build `django.db.models.Q` object for a queryset"""
        # e.g. 
        # where = {"or": [{'=': ['.request.user.id', 'id']}, {'>=': ['created', {'now': {}}]}]
        # filters = Q(id=123) | Q(created__gte=Now())
        if not where:
            return None

        where = RequestResolver.resolve(
            where,
            query=query,
            request=request
        )

        fitlers = DjangoFilter(where)
        try:
            return filters.value
        except FilterError as e:
            raise ResourceMisconfigured(
                f'{reosurce.id}: failed to build filters\n'
                f'Error: {e}'
            )

    def add_queryset_sorts(self, queryset, query, request=None, **context):
        """Add .order_by"""
        return queryset

    def add_queryset_filters(self, queryset, query, request=None, **context):
        """Add .filter"""
        return queryset

    def add_queryset_prefetches(self, queryset, query, request=None, **context):
        """Add .prefetch_related"""
        return queryset

    def add_queryset_annotations(self, queryset, query, request=None, **context):
        """Add .annotate"""
        return queryset

    def add_queryset_aggregations(self, queryset, query, request=None, **context):
        """Add .aggregate"""
        return queryset

    def add_queryset_pagination(self, queryset, query, request=None, **context):
        """Add limit/PK filter"""
        return queryset

    def add_queryset_fields(self, queryset, query, request=None, **context):
        """Add .only/.defer"""
        return queryset

    def add_queryset_distinct(self, queryset, query, request=None, **context):
        """Add .distinct if the query has left joins"""
        return queryset

    def get_queryset(self, query, request=None, **context):
        queryset = self.get_queryset_base(query, request=request, **context)
        for add in (
            'sorts',
            'filters',
            'prefetches',
            'annotations',
            'aggregations',
            'pagination',
            'fields',
            'distinct'
        ):
            queryset = getattr(self, f'add_queryset_{add}')(queryset, query, request=request, **context)
        return queryset

    def get_queryset_base(self, query, request=None, **context):
        resource = self.store.resource
        source = resource.source
        if isinstance(source, dict):
            where = source.get('where')
            source = source.get('model')
            if not model:
                raise ValueError('no model')
            filters = self.get_filters(resource, where, query, request)
        else:
            filters = None

        try:
            model = self.store.resolver.get_model(source)
        except SchemaResolverError as e:
            raise ResourceMisconfigured(
                f'{resource.id}: failed to resolve model from source "{source}"\n'
                f'Error: {e}'
            )

        if filters:
            try:
                queryset = model.objects.filter(filters)
            except Exception as e:
                raise ResourceMisconfigured(f'{resource.id}: cannot apply base filters')
        else:
            queryset = model.objects.all()

        return queryset

    def get(self, query, request=None, **context):
        """
            Arguments:
                query: query object
                request: request object
        """
        state = query.state
        if state.get('field'):
            return self.get_field(query, request=request, **context)
        elif state.get('record'):
            return self.get_record(query, request=request, **context)
        elif state.get('resource'):
            return self.get_resource(query, request=request, **context)
        else:
            raise ValueError('space execution is not supported')

    def get_resource(self, query, request=None, **context):
        if not self.can('resource.get', query, request):
            raise Forbidden()

        resource = self.store.resource
        source = resource.source
        meta = {}

        if not source:
            # no source -> do not use queryset
            if not resource.singleton:
                raise ResourceMisconfigured(
                    f'{resource.id}: cannot execute "get" on a collection with no source'
                )
            # singleton -> assume fields are all computed
            # e.g. user_id with source: ".request.user.id"
            data = self.serialize(resource, query, request, meta=meta)
        else:
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
            raise Forbidden()

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
            raise Forbidden()

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
