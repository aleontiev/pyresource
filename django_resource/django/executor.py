from django_resource.executor import Executor
from django_resource.translator import ResourceTranslator
from django_resource.resolver import RequestResolver, SchemaResolver
from django_resource.exceptions import (
    Forbidden,
    FilterError,
    ResourceMisconfigured,
    SerializationError,
    QueryValidationError,
    QueryExecutionError,
    NotFound,
    MethodNotAllowed
)
from django_resource.type_utils import get_link
from django.db.models import Prefetch, F, Value
from django.contrib.postgres.aggregates import ArrayAgg
from django_resource.utils import resource_to_django, make_literal
from .operators import make_expression, make_filter
from django_resource.conf import settings


class DjangoExecutor(Executor):
    @classmethod
    def get_sorts(cls, sorts, translate=None):
        if isinstance(sorts, str):
            sorts = [sorts]

        if not sorts:
            return None

        results = []
        for sort in sorts:
            desc = False
            if sort.startswith('-'):
                sort = sort[1:]
                desc = True
            if translate:
                sort = ResourceTranslator.translate(
                    sort,
                    translate
                )

            sort = resource_to_django(sort)
            if desc:
                # add descending sort marker
                sort = f'-{sort}'
            results.append(sort)
        return results

    @classmethod
    def get_filters(cls, resource, where, query=None, request=None, translate=False):
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
    def add_queryset_sorts(
        cls, resource, fields, queryset, query, request=None, level=None, related=None, **context,
    ):
        """Add .order_by"""
        source = cls.get_queryset_source(resource, related=related)
        sorts = None
        if isinstance(source, dict):
            qs = source.get("queryset")
            sort = qs.get("sort", None)
            sorts = cls.get_sorts(sort)

        state = cls.get_query_state(query, level=level)
        sort = state.get("sort", None)
        if sort:
            sorts = cls.get_sorts(sort, translate=resource)

        # order by request sorts, or by default sorts
        if sorts:
            queryset = queryset.order_by(*sorts)
        return queryset

    @classmethod
    def add_queryset_filters(
        cls, resource, fields, queryset, query, request=None, level=None, related=None, **context,
    ):
        """Add .filter"""
        source = cls.get_queryset_source(resource, related=related)
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
                resource,
                where,
                query=query,
                request=request,
                translate=True
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
        cls,
        resource,
        fields,
        queryset,
        query,
        level=None,
        resolver=None,
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
        state = cls.get_query_state(query, level=level)
        prefetches = []
        take = state.get('take', {})
        root_field = query.state.get('field', None) if level is None else None
        take_root = root_field is not None and query.state.get('take') is not None
        if take or take_root:
            for field in fields:
                take_field = take.get(field.name)
                if take_root or (take_field and isinstance(take_field, dict)):
                    source = SchemaResolver.get_field_source(field.source)
                    source = resource_to_django(source)
                    related = field.related
                    related_level = f'{level}.{field.name}' if level else field.name
                    related_fields = cls.select_fields(
                        related, action="get", query=query, request=request, level=related_level
                    )
                    next_queryset = cls.get_queryset(
                        resolver,
                        related,
                        related_fields,
                        query,
                        request=request,
                        level=related_level,
                        **context
                    )
                    prefetches.append(
                        Prefetch(source, queryset=next_queryset, to_attr=f'.{field.name}')
                    )

        if prefetches:
            queryset = queryset.prefetch_related(*prefetches)
        return queryset

    @classmethod
    def add_queryset_pagination(
        cls,
        resource,
        fields,
        queryset,
        query,
        count=None,
        level=None,
        **context,
    ):
        """Add pagination"""
        if level is not None:
            return queryset

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
    def make_annotation(
        cls, field, **context
    ):
        is_list = field.is_list
        source = SchemaResolver.get_field_source(field.source)
        if isinstance(source, str):
            # string annotation e.g. "user.name"
            source = resource_to_django(source)
            if is_list:
                kwargs = {}
                # optional ordering
                if isinstance(field.source, dict):
                    qs = field.source.get('queryset')
                    sort = qs.get('sort', None) if qs else None
                    if sort:
                        sort = f'{source}.{sort}'
                        kwargs['ordering'] = resource_to_django(sort)

                # TODO: support backends besides Postgres
                # should be doable with custom aggregates
                return ArrayAgg(source, **kwargs)
            else:
                return F(source)
        else:
            # functional annotation e.g. {"count": "location.users"}
            return make_expression(field.source)

    @classmethod
    def add_queryset_fields(
        cls, resource, fields, queryset, query, level=None, **context,
    ):
        """Add fields

        All of a Resource's fields represented in a queryset ("resourced fields")
        are annotated with a prefix of "." in order to prevent
        naming conflicts between source and resourced fields
        """
        annotations = {}
        state = cls.get_query_state(query, level=level)
        take = state.get('take', None)
        root_field = query.state.get('field', None) if level is None else None
        root_take = query.state.get('take', None)
        for field in fields:
            if root_field:
                if root_take:
                    # ignore field being prefetched
                    break
            else:
                if take and isinstance(take.get(field.name), dict):
                    # ignore fields being prefetched
                    continue

            annotations[f'.{field.name}'] = cls.make_annotation(
                field,
                **context
            )

        if annotations:
            queryset = queryset.annotate(**annotations)
        return queryset.only('pk')

    @classmethod
    def add_queryset_distinct(
        cls, resource, fields, queryset, query, **context,
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
        cls, resolver, resource, fields, query, **context,
    ):
        queryset = cls.get_queryset_base(resolver, resource, **context)
        for add in (
            "prefetches",
            "fields",
            "filters",
            "sorts",
            "distinct",
            "pagination",
        ):
            queryset = getattr(cls, f"add_queryset_{add}")(
                resource, fields, queryset, query, resolver=resolver, **context,
            )
        # print(str(queryset.query))
        return queryset

    @classmethod
    def get_queryset_source(self, resource, related=None):
        if related and isinstance(related.source, dict) and 'queryset' in related.source:
            source = related.source
            source['queryset']['model'] = resource.source
        else:
            source = resource.source
        return source

    @classmethod
    def get_queryset_base(cls, resolver, resource, related=None, **context):
        source = cls.get_queryset_source(resource, related=related)

        try:
            model = resolver.get_model(source)
        except SchemaResolverError as e:
            raise ResourceMisconfigured(
                f'{resource.id}: failed to resolve model from source "{source}"\n'
                f"Error: {e}"
            )
        return model.objects.all()

    def _get_resources(self, type, query, request=None, prefix=None, **context):
        """Get many resources from a server or space perspective"""
        if type == "server":
            root = context.get("server") or self.store.server
            child_name = "space"
        elif type == "space":
            root = context.get("space") or self.store.space
            child_name = "resource"

        children = getattr(root, f"{child_name}s_by_name")
        take = query.state.get("take")
        data = {}
        meta = {}
        for name, child in children.items():
            shallow = True
            if take is not None:
                if not take.get(name, False):
                    continue
                if isinstance(take[name], dict):
                    shallow = False
            if shallow:
                data[name] = f"./{name}/"
            else:
                subquery = getattr(query.get_subquery(level=name), child_name)(name)
                subprefix = name if prefix is None else f"{prefix}.{name}"
                context[child_name] = child
                subdata = getattr(self, f"get_{child_name}")(
                    subquery, request=request, prefix=subprefix, **context
                )
                # merge the data
                data[name] = subdata["data"]
                # merge the metadata if it exists
                self.merge_meta(meta, subdata.get("meta"), name)

        result = {"data": data}
        if meta:
            result["meta"] = meta
        return result

    def _get_resource(
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
                    resolver, resource, fields, query, request=request, **context
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
        return self._get_resource("record", query, request=request, **context)

    def get_field(self, query, request=None, **context):
        return self._get_resource("field", query, request=request, **context)

    def get_server(self, query, request=None, prefix=None, server=None, **context):
        return self._get_resources(
            "server", query, request=request, prefix=prefix, **context
        )

    def get_space(self, query, request=None, prefix=None, **context):
        return self._get_resources(
            "space", query, request=request, prefix=prefix, **context
        )

    def get_resource(self, query, request=None, **context):
        return self._get_resource("resource", query, request=request, **context)

    def explain_resource(self, query, request=None, resource=None, **context):
        resource = resource or self.store.resource
        return {'data': {'resource': resource.serialize()}}

    def explain_record(self, query, **context):
        return self.explain_resource(query, **context)

    def explain_server(self, query, request=None, **context):
        server = self.store.server
        return {'data': {'server': server.serialize()}}

    def explain_field(self, query, request=None, resource=None, **context):
        resource = resource or self.store.resource
        field = query.state.get('field')
        field = resource.fields_by_name[field]
        return {'data': {'field': field.serialize()}}

    def explain_space(self, query, request=None, space=None, **context):
        space = space or self.store.space
        return {'data': {'space': space.serialize()}}

    def add_resource(self, query, request=None, resource=None, **context):
        if resource is None:
            resource = self.store.resource

        if not self.can(resource, "add.resource", query, request):
            raise Forbidden()

        source = resource.source
        resolver = self.store.resolver
        model = resolver.get_model(source)

        fields = self.select_fields(
            resource, action="add", query=query, request=request,
        )
        data = query.state.get('data')
        as_list = True
        if not isinstance(data, list):
            data = [data]
            as_list = False

        # build up instances
        # TODO: support partial success on lists
        instances = []
        for i, dat in enumerate(data):
            instance = model()
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
                        raise BadRequest(f'Expecting to find field {field.id}')
                # 2. validate value
                try:
                    field.validate(field.type, value)
                except Exception as e:
                    raise BadRequest(f'{value} is invalid for field {field.id} with type {field.type}')

                source = resolver.get_field_source(field.source)
                if not source:
                    raise BadRequest(f'Cannot add field {field.id} without source')

                if '.' in source:
                    raise BadRequest(f'Cannot add through nested source {source}')

                if resolver.is_field_local(model, source):
                    # this is a "local" field that lives on the model itself
                    setattr(instance, source, value)
                else:
                    # this is a "remote" field that is local to another model
                    # which means we cannot set the relationship until after creation
                    if not hasattr(instance, '_add_after'):
                        instance._add_after = {}
                    instance._add_after[field.name] = (field, value)

        ids = []
        # save instances and their new IDs
        for instance in instances:
            try:
                instance.save()
                if hasattr(instance, '_add_after'):
                    for field, value in instance._add_after.values():
                        source = resolver.get_field_source(field.source)
                        # TODO: what if this isnt a many-related-manager?
                        # is that possible for a remote field?
                        getattr(instance, source).set(value)
                ids.append(instance.pk)
            except Exception as e:
                raise BadRequest(str(e))

        take = query.state.get('take', None)
        if take:
            # perform a get.record or get.resource to get the created records
            query = query.action('get')
            if as_list:
                query = query.where({
                    'in': [resource.id_name, make_literal(ids)]
                })
            else:
                query = query.record(ids[0])
            return query.get(request=request, **context)
        else:
            return True

    def add_field(self, query, request=None, **context):
        return

    def add_space(self, query, request=None, **context):
        return self._add_resources('space', query, request=request, **context)

    def add_server(self, query, request=None, **context):
        return self._add_resources('server', query, request=request, **context)

    def _add_resources(self, type, query, request=None, **context):
        return

    def add_record(self, query, **context):
        raise MethodNotAllowed()
