from django_resource.store import Executor, RequestResolver
from django_resource.exceptions import (
    Forbidden,
    FilterError,
    ResourceMisconfigured,
    SerializationError,
)
from .filters import DjangoFilter
from django_resource.utils import get
from django_resource.conf import settings
from django_resource.type_utils import get_link


class DjangoExecutor(Executor):
    def get_filters(self, resource, where, query, request):
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
            "sorts",
            "filters",
            "prefetches",
            "annotations",
            "aggregations",
            "pagination",
            "fields",
            "distinct",
        ):
            queryset = getattr(self, f"add_queryset_{add}")(
                queryset, query, request=request, **context
            )
        return queryset

    def get_queryset_base(self, query, request=None, **context):
        resource = self.store.resource
        source = resource.source
        if isinstance(source, dict):
            where = source.get("where")
            source = source.get("model")
            if not source:
                raise ValueError("no model/source")
            filters = self.get_filters(resource, where, query, request)
        else:
            filters = None

        try:
            model = self.store.resolver.get_model(source)
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

    def get(self, query, request=None, **context):
        """
            Arguments:
                query: query object
                request: request object
        """
        state = query.state
        if state.get("field"):
            return self.get_field(query, request=request, **context)
        elif state.get("record"):
            return self.get_record(query, request=request, **context)
        elif state.get("resource"):
            return self.get_resource(query, request=request, **context)
        else:
            raise ValueError("space execution is not supported")

    def get_resource_by_name(self, name):
        space = self.store.get_space()
        if not space:
            raise SerializationError(
                f'Cannot lookup resource "{name}"; store has no space'
            )
        resource = space.resources_by_name.get(name)
        if not resource:
            raise SerializationError(f'Resource "{name}" not found')
        return resource

    def get_resource(self, query, request=None, **context):
        if not self.can("get.resource", query, request):
            raise Forbidden()

        resource = self.store.resource
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
            if resource.singleton:
                # get queryset and obtain first record
                record = self.get_queryset(query, request=request, **context).first()
                if not record:
                    raise ResourceMisconfigured(
                        f"{resource.id}: could not locate record for singleton resource"
                    )
                data = self.serialize(
                    resource, query=query, request=request, record=record, meta=meta
                )
            else:
                queryset = self.get_queryset(query, request=request, **context)
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
        can = self.can("get.record", query=query, request=request)
        if not can:
            raise Forbidden()

        queryset = self.get_queryset(query, request=request, can=can, **context)
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
        if not self.can("get.field", query, request):
            raise Forbidden()

        if query.state.get("take"):
            # use get_related to return related data
            # this requires "prefetch" permission on this field
            # or "get.prefetch" permission on the related field
            return self.get_related(query, request=request, **context)

        queryset = self.get_queryset(query, request=request, **context)

    def get_related(self, query, request=None, **context):
        pass  # TODO

    def should_take_field(self, field, take):
        """Return True if the field should be taken as requested"""
        if take is not None:
            # if provided, use "take" to refine field selection
            defaults = take.get("*", False)
            should_take = take.get(field.name, None)
            if should_take is False:
                # explicitly requested not to take this
                return False
            if should_take is None:
                # no explicit request: default mode
                if field.lazy or not defaults:
                    return False
            return True
        else:
            return not field.lazy

    def get_fields(
        self, resource, action, level=None, query=None, request=None
    ):
        """Get a subset of a resource's fields to be used for an action

        Arguments:
            resource: a Resource
            action: action string (ex: "get")
            level: level string (ex: "a.b")
            query: a Query
            record: a Django model instance
            request: a Django Request object
        """
        # TODO: cache result by all arguments
        # this allows serialization and get_queryset to re-use the same field definitions
        result = []
        fields = resource.fields
        state = query.get_state(level=level)
        take = state.get("take")
        for field in fields:
            # use query filters (take)
            if not self.should_take_field(field, take):
                continue

            # use permission filters (can)
            # pass in the record, query, and request as context
            if not self.can_take_field(
                field, action, query=query, request=request
            ):
                continue
            result.append(field)
        return result

    def to_json_value(self, value):
        """Get a JSON-compatible representation of the given value"""
        if isinstance(value, list):
            return [self.to_json_value(v) for v in value]

        if isinstance(value, dict):
            return {
                self.to_json_value(k): self.to_json_value(v) for k, v in value.items()
            }

        if isinstance(value, (bool, str, int, float)) or value is None:
            # whitelisted types: return as-is
            # JSON can support these natively
            return value

        # special handling for files (FieldField fields, FieldFile values)
        # check for and use .url property if it exists
        try:
            url = getattr(value, "url", None)
        except Exception:
            # there is a url property , but could not resolve it
            return None
        else:
            # there is no url property
            if url is not None:
                value = url

        # stringify everything else
        # e.g. datetime, time, uuid, model instances, etc
        return str(value)

    def serialize_value(self, value):
        """Shallow serialization

        Return serialized representation of record or list of records;
        - Represent all records by primary key (hence shallow)
        - Prepare result for JSON
        """
        if isinstance(value, list):
            value = [getattr(v, "pk", v) for v in value]
        else:
            value = getattr(value, "pk", value)
        return self.to_json_value(value)

    def serialize(
        self, resource, record=None, query=None, level=None, request=None, meta=None
    ):
        """Deep serialization

        Arguments:
            resource: a Resource
            record: a dict or list of dicts
            query: a Query
            level: a level string
            request: a Django request
            meta: a metadata dict

        Returns:
            Serialized representation of record or list of records
        """
        fields = self.get_fields(
            resource,
            action="get",
            level=level,
            query=query,
            request=request,
        )
        results = []
        state = query.get_state(level)
        page_size = state.get("page", {}).get("size", settings.DEFAULT_PAGE_SIZE)
        take = state.get("take")

        as_list = False
        if isinstance(record, list):
            as_list = True
            records = record
        else:
            records = [record]

        for record in records:
            result = {}
            for field in fields:
                name = field.name
                type = field.type
                # string-type source indicates a renamed basic field
                # dict-type source indicates a computed field (e.g. concat of 2 fields)
                source = field.source if isinstance(field.source, str) else name
                context = {"fields": record, "request": request, "query": query.state}
                if isinstance(source, dict):
                    # get from context
                    value = execute(source, context)
                else:
                    if record:
                        # get from record provided
                        value = get(source, record)
                    else:
                        # get from context (request/query data)
                        if source.startswith("."):
                            source = source[1:]
                        else:
                            raise SerializationError(
                                f"Source {source} must start with . because no record"
                            )
                        value = get(source, context)

                if hasattr(value, "all") and callable(value.all):
                    # account for Django many-related managers
                    value = list(value.all())

                if take is not None:
                    take_field = take.get(name, None)
                    if isinstance(take_field, dict):
                        # serialize this recursively as an object
                        link = get_link(type)
                        if not link:
                            raise SerializationError(
                                f'Cannot serialize relation for field "{resource.id}.{name}" with type {type}\n'
                                f"Error: type has no link"
                            )
                        related = self.get_resource_by_name(link)
                        if level is None:
                            next_level = name
                        else:
                            next_level = f"{level}.{name}"

                        if isinstance(value, list):
                            if len(value) > page_size:
                                # TODO: add pagination markers for this relationship
                                # and do not render the next element
                                value = value[:page_size]

                        value = self.serialize(
                            related,
                            record=value,
                            query=query,
                            request=request,
                            level=next_level,
                            meta=meta,
                        )
                    else:
                        # take[name] is True ->
                        # serialize the field or pk if instance
                        value = self.serialize_value(value)
                else:
                    # take is None -> serialize the value or pk if instance
                    value = self.serialize_value(value)

                result[name] = value

            results.append(result)

        if not as_list:
            results = results[0]
        return results

    def can_take_field(self, field, action, query=None, request=None):
        can = field.can
        if can is not None:
            if action in can:
                can = can[action]
                if isinstance(can, dict):
                    can = execute(
                        can,
                        {"request": request, "query": query.state}
                    )
                return can
            return False
        else:
            return True

    def can(self, action, query=None, request=None):
        return True  # TODO
