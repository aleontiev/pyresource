from .exceptions import SerializationError
from .conf import settings
from .utils import get
from .type_utils import get_link


class Executor:
    """Executes Query, returns dict response"""
    def __init__(self, store, **context):
        self.store = store
        self.context = context

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
            raise QueryExecutionError("space execution is not supported")

    @classmethod
    def resolve_resource(cls, base_resource, name):
        space = base_resource.space
        if not space:
            raise SerializationError(
                f'Cannot lookup resource named "{name}" from base resource "{base_resource.id}"'
            )
        resource = space.resources_by_name.get(name)
        if not resource:
            raise SerializationError(f'Resource "{name}" not found')
        return resource

    @classmethod
    def select_fields(
        cls, resource, action, level=None, query=None, request=None
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
            if not cls.should_take_field(field, take):
                continue

            # use permission filters (can)
            # pass in the record, query, and request as context
            if not cls.can_take_field(
                field, action, query=query, request=request
            ):
                continue
            result.append(field)
        return result

    @classmethod
    def can_take_field(cls, field, action, query=None, request=None):
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

    @classmethod
    def should_take_field(cls, field, take):
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

    @classmethod
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

    @classmethod
    def serialize_value(cls, value):
        """Shallow serialization

        Return serialized representation of record or list of records;
        - Represent all records by primary key (hence shallow)
        - Prepare result for JSON
        """
        if isinstance(value, list):
            value = [getattr(v, "pk", v) for v in value]
        else:
            value = getattr(value, "pk", value)
        return cls.to_json_value(value)

    @classmethod
    def serialize(
        cls,
        resource,
        record=None,
        query=None,
        level=None,
        request=None,
        meta=None
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
        fields = cls.select_fields(
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
                        related = cls.resolve_resource(resource, link)
                        if level is None:
                            next_level = name
                        else:
                            next_level = f"{level}.{name}"

                        if isinstance(value, list):
                            if len(value) > page_size:
                                # TODO: add pagination markers for this relationship
                                # and do not render the next element
                                value = value[:page_size]

                        value = cls.serialize(
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
                        value = cls.serialize_value(value)
                else:
                    # take is None -> serialize the value or pk if instance
                    value = cls.serialize_value(value)

                result[name] = value

            results.append(result)

        if not as_list:
            results = results[0]
        return results

    @classmethod
    def can(cls, resource, action, query=None, request=None):
        return True  # TODO
