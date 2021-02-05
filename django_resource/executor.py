import base64
import json
import copy

from .exceptions import SerializationError, MethodNotAllowed
from .conf import settings
from .resolver import SchemaResolver
from .utils import get
from .features import LEVELED_FEATURES, ROOT_FEATURES
from .type_utils import get_link


class Executor:
    """Executes Query, returns dict response"""

    def __init__(self, store, **context):
        self.store = store
        self.context = context

    def add(self, query, **context):
        return self._act('add', query, **context)

    def explain(self, query, **context):
        """
            Arguments:
                query: query object
        """
        return self._act('explain', query, **context)

    def get(self, query, **context):
        """
            Arguments:
                query: query object
        """
        return self._act('get', query, **context)

    def _act(self, name, query, **context):
        state = query.state
        endpoint = None
        if state.get("field"):
            endpoint = 'field'
        elif state.get("record"):
            endpoint = 'record'
        elif state.get("resource"):
            endpoint = 'resource'
        elif state.get("space"):
            endpoint = 'space'
        else:
            endpoint = 'server'

        action_name = f'{name}_{endpoint}'
        action = getattr(self, action_name, None)
        if not action:
            raise NotImplementError(
                f'{self.__class__} does not implement "{action_name}"'
            )
        return action(query, **context)

    @classmethod
    def decode_cursor(self, cursor):
        return json.loads(base64.b64decode(cursor.decode("utf-8")))

    @classmethod
    def encode_cursor(self, cursor):
        return base64.b64encode(json.dumps(cursor).encode("utf-8"))

    @classmethod
    def get_next_page(cls, query, offset=None, level=None):
        # TODO: support keyset pagination
        state = cls.get_query_state(query, level=level)
        page = state.get("page", {})
        size = int(page.get("size", settings.DEFAULT_PAGE_SIZE))
        page = page.get("after", None)
        if page is not None:
            page = cls.decode_cursor(page)

        # offset-limit pagination
        if offset is None:
            offset = size
        if page is None:
            next_offset = offset
        else:
            next_offset = page.get("offset", 0) + offset
        return cls.encode_cursor({"offset": next_offset})

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

    # TODO: @cache results by all arguments to avoid recomputing this across different phases
    # of the same request (e.g. serialization and query building)
    @classmethod
    def select_fields(cls, resource, action, level=None, query=None, request=None):
        """Get a subset of a resource's fields to be used for an action

        Arguments:
            resource: a Resource
            action: action string (ex: "get")
            level: level string (ex: "a.b")
            query: a Query
            record: a Django model instance
            request: a Django Request object
        """
        result = []
        fields = resource.fields
        # if this is a field-oriented request
        take_field = query.state.get("field")
        state = cls.get_query_state(query, level=level)
        take = state.get("take")

        for field in fields:
            if take_field and level is None:
                # take this field only
                if field.name == take_field:
                    if not cls.can_take_field(
                        field, action, query=query, request=request
                    ):
                        raise MethodNotAllowed()
                    return [field]
                continue

            # many fields

            # use query filters (take)
            if not cls.should_take_field(field, take):
                continue

            # use permission filters (can)
            # pass in the record, query, and request as context
            if not cls.can_take_field(field, action, query=query, request=request):
                continue
            result.append(field)
        return result

    @classmethod
    def can(cls, resource, action, query=None, request=None):
        """Whether or not the given action is authorized

        Arguments:
            resource: a Resource
            action: an endpoint-qualified string action (e.g. "get.resource")
            query: a Query
            request: a Django request
        Returns:
            True: the action is authorized for all records
            False: the action is not authorized
            dict: the action may be authorized for some records
                e.g: {'true': 'is_active'}
        """
        return True  # TODO

    @classmethod
    def can_take_field(cls, field, action, query=None, request=None):
        can = field.can
        if can is not None:
            if action in can:
                can = can[action]
                if isinstance(can, dict):
                    can = execute(can, {"request": request, "query": query.state})
                return can
            return False
        else:
            return True

    @classmethod
    def should_take_field(cls, field, take):
        """Return True if the field should be taken as requested"""
        if take is not None:
            # if provided, use "take" to refine field selection
            take_defaults = take.get("*", False)
            should_take = take.get(field.name, None)
            if should_take is False:
                # explicitly requested not to take this
                return False
            if should_take is None:
                # no explicit request: default mode
                if field.lazy or not take_defaults:
                    return False
            return True
        else:
            # if not, take the field unless it is lazy
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
    def get_query_state(cls, query, level=None):
        root = query.state
        field = root.get('field')
        if not field:
            return query.get_state(level)

        state = None
        if level is None:
            # no state at the root, use initial state
            # remove all of the leveled features
            state = copy.copy(root)
            for feature in LEVELED_FEATURES:
                state.pop(feature, None)
        else:
            # shift th elevel, remove root features
            level = level.split(".")[1:] or None
            state = query.get_state(level)
            state = copy.copy(state)
            for feature in ROOT_FEATURES:
                state.pop(feature, None)

        return state

    @classmethod
    def serialize(
        cls,
        resource,
        fields,
        record=None,
        query=None,
        level=None,
        request=None,
        meta=None,
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
        results = []
        state = cls.get_query_state(query, level=level)
        field_name = query.state.get('field', None)
        page_size = state.get("page", {}).get("size", settings.DEFAULT_PAGE_SIZE)
        take = state.get("take")

        as_list = False
        if isinstance(record, list):
            as_list = True
            records = record
        else:
            records = [record]

        if records is None:
            # special case for a singleton without a source
            records = [None]

        is_field_root = bool(field_name and not level)
        for record in records:
            result = {}
            for field in fields:
                name = field.name
                type = field.type
                use_context = True
                if record:
                    # get from record provided
                    # use special .name properties that are added as annotations
                    try:
                        value = getattr(record, f'.{name}')
                        use_context = False
                    except AttributeError as e:
                        if f'.{name}' not in str(e):
                            raise

                if use_context:
                    # get from context (request/query data)
                    source = SchemaResolver.get_field_source(field.source) or name
                    if source.startswith("."):
                        context = {"fields": record, "request": request, "query": query.state}
                        source = source[1:]
                    else:
                        if record is None:
                            raise SerializationError(
                                f"Source {source} must start with . because no record"
                            )
                        context = record
                    value = get(source, context)

                if hasattr(value, "all") and callable(value.all):
                    # account for Django many-related managers
                    value = list(value.all())

                if (is_field_root and query.state.get("take")) or (
                    take is not None and isinstance(take.get(name), dict)
                ):
                    # deep serialization
                    link = get_link(type)
                    if link:
                        related = cls.resolve_resource(resource, link)
                        if level is None:
                            related_level = name
                        else:
                            related_level = f"{level}.{name}"

                        if isinstance(value, list):
                            if len(value) > page_size:
                                # TODO: add pagination markers for this relationship
                                # and do not render the next element
                                value = value[:page_size]

                        related_fields = cls.select_fields(
                            related,
                            action="get",
                            level=related_level,
                            query=query,
                            request=request,
                        )
                        value = cls.serialize(
                            related,
                            related_fields,
                            level=related_level,
                            record=value,
                            query=query,
                            request=request,
                            meta=meta,
                        )
                    elif field_name is None:
                        raise SerializationError(
                            f'Cannot serialize relation for field "{resource.id}.{name}" with type {type}\n'
                            f"Error: type has no link"
                        )
                    else:
                        value = cls.serialize_value(value)
                else:
                    # shallow serialization
                    value = cls.serialize_value(value)

                result[name] = value

            results.append(result)

        if is_field_root:
            # return one field only
            results = [result[field_name] for result in results]

        if not as_list:
            results = results[0]
        return results

    @classmethod
    def merge_meta(cls, meta, other, name):
        if not other:
            return
        meta.update(other)
