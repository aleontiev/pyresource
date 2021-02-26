import base64
import json
import copy

from .exceptions import SerializationError, MethodNotAllowed, RequestError, ResourceMisconfigured
from .conf import settings
from .resolver import SchemaResolver, RequestResolver
from .response import Response
from .utils import get
from .expression import execute
from .features import LEVELED_FEATURES, ROOT_FEATURES
from .utils.types import get_link


def get_executor_class(engine):
    if engine == 'django':
        from .django.executor import DjangoExecutor
        return DjangoExecutor
    elif engine == 'api':
        raise NotImplementedError()
    elif engine == 'resource':
        raise NotImplementedError()
    else:
        raise NotImplementedError()


class Inspection:
    @classmethod
    def _get_query_state(cls, query, level=None):
        root = query.state
        field = root.get("field")
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
            # shift the level, remove root features
            level = level.split(".")[1:] or None
            state = query.get_state(level)
            state = copy.copy(state)
            for feature in ROOT_FEATURES:
                state.pop(feature, None)

        return state

    @classmethod
    def _merge_meta(cls, meta, other, name):
        if not other:
            return
        meta.update(other)


class Selection:
    # TODO: @cache results by all arguments to avoid recomputing this across different phases
    # of the same request (e.g. serialization and query building)
    @classmethod
    def _take_fields(cls, resource, action, level=None, query=None, request=None):
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
        state = cls._get_query_state(query, level=level)
        if state is True:
            # link/list, get ID only
            take = {
                resource.id_name: True
            }
        else:
            take = state.get("take")

        for field in fields:
            if take_field and level is None:
                # take this field only
                if field.name == take_field:
                    if not cls._can_take_field(
                        field, action, query=query, request=request
                    ):
                        raise MethodNotAllowed()
                    return [field]
                continue

            # many fields

            # use query filters (take)
            if not cls._should_take_field(field, take):
                continue

            # use permission filters (can)
            # pass in the record, query, and request as context
            if not cls._can_take_field(field, action, query=query, request=request):
                continue
            result.append(field)
        return result

    @classmethod
    def _should_take_field(cls, field, take):
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


class Authorization:
    @classmethod
    def _can(cls, resource, action, query=None, request=None, field=None):
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
        if field:
            if field.can and isinstance(field.can, dict) and field.can.get('prefetch'):
                # permission to prefetch granted by this field
                prefetch = field.can['prefetch']
                if prefetch is True:
                    return True
                else:
                    prefetch = RequestResolver.resolve(
                        prefetch,
                        request=request,
                        query=query
                    )
                    if prefetch is True:
                        return True
                    elif prefetch:
                        # TODO: support functional type and apply it during serialization
                        raise ResourceMisconfigured(
                            f'{field.id}.prefetch: '
                            f'must resolve to simple type, not {prefetch}'
                        )

        can = resource.can
        if can is None:
            # resource has no permissions defined
            # -> assume this can be done
            return True

        clauses = []
        action = action.lower()
        action_name, endpoint_name = action.split('.')
        # look for matching clauses
        for key, value in can.items():
            # key can be:
            # *: match every action/endpoint combination possible
            # get: match every endpoint for action = get
            # *.field: match every action for endpoint = field
            # get.field: match field endpoint for action = get
            # get, set: match every endpoint for action = get and also action = set
            parts = key.split(',')
            for part in parts:
                part = part.strip().lower()
                if '.' in part:
                    # must have only one .
                    action_part, endpoint_part = part.split('.')
                    # a.b or *.a or a.*
                    if part == action or (
                        action_part == '*' and endport_part == endpoint_name
                    ) or (
                        endpoint_part == '*' and action_part == action_name
                    ):
                        clauses.append((key, value))
                        break
                else:
                    if part == '*' or part == action_name:
                        clauses.append((key, value))
                        break

        result = []
        for key, clause in clauses:
            try:
                clause = RequestResolver.resolve(clause, query=query, request=request)
            except Exception as e:
                raise ResourceMisconfigured(
                    f'{resource.id}: failed to resolve can (key = {key}, clause = {clause})\n'
                    f'{e.__class__.__name__}: {e}'
                )
            if clause:
                if clause is True:
                    return True
                result.append(clause)

        if result:
            # return an object which means allowed to access certain records
            # depending on the filter
            result = {'or': result} if len(result) > 1 else result[0]
            return result
        else:
            return False

    @classmethod
    def _can_take_field(cls, field, action, query=None, request=None):
        can = field.can
        default = settings.FIELD_CAN
        depends = field.depends

        if can is None:
            can = default
        elif default is not None:
            default = copy.copy(default)
            default.update(can)
            can = default

        if depends is not None:
            # if this fields has a "depends", it is an expression that must evaluate truthy
            ok = execute(depends, {"request": request, "query": query.state, "globals": settings})
            if not ok:
                return False

        if can is not None:
            if action in can:
                can = can[action]
                if isinstance(can, dict):
                    can_dict = can
                    can = execute(can, {"request": request, "query": query.state, "globals": settings})
                return can
            return False
        else:
            return True


class Serialization:
    @classmethod
    def _to_json_value(self, value):
        """Get a JSON-compatible representation of the given value"""
        if isinstance(value, (list, tuple)):
            return [self._to_json_value(v) for v in value]

        if isinstance(value, dict):
            return {
                self._to_json_value(k): self._to_json_value(v) for k, v in value.items()
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
    def _serialize_value(cls, value):
        """Shallow serialization

        Return serialized representation of record or list of records;
        - Represent all records by primary key (hence shallow)
        - Prepare result for JSON
        """
        if isinstance(value, list):
            value = [getattr(v, "pk", v) for v in value]
        else:
            value = getattr(value, "pk", value)
        return cls._to_json_value(value)

    @classmethod
    def _resolve_resource(cls, base_resource, name):
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
    def _serialize(
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
        state = cls._get_query_state(query, level=level)
        field_name = query.state.get("field", None)
        page_size = state.get("page", {}).get("size", settings.PAGE_SIZE)
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
                        value = getattr(record, f".{name}")
                        use_context = False
                    except AttributeError as e:
                        if f".{name}" not in str(e):
                            raise

                if use_context:
                    # get from context (request/query data)
                    source = SchemaResolver.get_field_source(field.source) or name
                    if source.startswith("."):
                        context = {
                            "fields": record,
                            "request": request,
                            "query": query.state,
                        }
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
                        related = cls._resolve_resource(resource, link)
                        if level is None:
                            related_level = name
                        else:
                            related_level = f"{level}.{name}"

                        if isinstance(value, list):
                            if len(value) > page_size:
                                # TODO: add pagination markers for this relationship
                                # and do not render the next element
                                value = value[:page_size]

                        related_fields = cls._take_fields(
                            related,
                            action="get",
                            level=related_level,
                            query=query,
                            request=request,
                        )
                        value = cls._serialize(
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
                        value = cls._serialize_value(value)
                else:
                    # shallow serialization
                    value = cls._serialize_value(value)

                result[name] = value

            results.append(result)

        if is_field_root:
            # return one field only
            results = [result[field_name] for result in results]

        if not as_list:
            results = results[0]
        return results


class Pagination:
    @classmethod
    def _decode_cursor(self, cursor):
        return json.loads(base64.b64decode(cursor.decode("utf-8")))

    @classmethod
    def _encode_cursor(self, cursor):
        return base64.b64encode(json.dumps(cursor).encode("utf-8"))

    @classmethod
    def _get_next_page(cls, query, offset=None, level=None):
        # TODO: support keyset pagination
        state = cls._get_query_state(query, level=level)
        page = state.get("page", {})
        size = int(page.get("size", settings.PAGE_SIZE))
        page = page.get("after", None)
        if page is not None:
            page = cls._decode_cursor(page)

        # offset-limit pagination
        if offset is None:
            offset = size
        if page is None:
            next_offset = offset
        else:
            next_offset = page.get("offset", 0) + offset
        return cls._encode_cursor({"offset": next_offset})


class Dispatch:
    def _act(self, name, query, **context):
        state = query.state
        endpoint = None
        if state.get("field"):
            endpoint = "field"
        elif state.get("record"):
            endpoint = "record"
        elif state.get("resource"):
            endpoint = "resource"
        elif state.get("space"):
            endpoint = "space"
        else:
            endpoint = "server"

        action_name = f"{name}_{endpoint}"
        action = getattr(self, action_name, None)
        if context.get("response"):
            # return as a response
            success = {"add": 201, "delete": 204}.get(name, 200)
            try:
                return Response(action(query, **context), code=success)
            except RequestError as e:
                return Response(str(e), code=e.code)
            except Exception as e:
                return Response(str(e), code=500)
        else:
            return action(query, **context)


class Executor(
    Dispatch, Inspection, Selection, Serialization, Authorization, Pagination
):
    """Executes Query, returns dict response"""

    def __init__(self, **context):
        self.context = context

    def add(self, query, **context):
        return self._act("add", query, **context)

    def explain(self, query, **context):
        """
            Arguments:
                query: query object
        """
        return self._act("explain", query, **context)

    def get(self, query, **context):
        """
            Arguments:
                query: query object
        """
        return self._act("get", query, **context)


class MultiExecutor(Executor):
    def _get_resources(self, type, query, request=None, prefix=None, **context):
        """Get many resources from a server or space perspective"""
        server = query.server
        if type == "server":
            root = context.get("server") or server
            child_name = "space"
        elif type == "space":
            space_name = query.state.get('space')
            root = context.get("space") or server.spaces_by_name[space_name]
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
                executor = server.get_executor(subquery, prefix=subprefix)
                subdata = getattr(executor, f"get_{child_name}")(
                    subquery, request=request, prefix=subprefix, **context
                )
                # merge the data
                data[name] = subdata["data"]
                # merge the metadata if it exists
                self._merge_meta(meta, subdata.get("meta"), name)

        result = {"data": data}
        if meta:
            result["meta"] = meta
        return result


class SpaceExecutor(MultiExecutor):
    def get_space(self, query, request=None, prefix=None, **context):
        return self._get_resources(
            "space", query, request=request, prefix=prefix, **context
        )

    def explain_space(self, query, request=None, space=None, **context):
        server = query.server
        space_name = query.state.get('space')
        space = space or server.spaces_by_name[space_name]
        return {"data": {"space": space.serialize()}}


class ServerExecutor(MultiExecutor):
    def get_server(self, query, request=None, prefix=None, server=None, **context):
        return self._get_resources(
            "server", query, request=request, prefix=prefix, **context
        )

    def explain_server(self, query, request=None, **context):
        server = query.server
        return {"data": {"server": server.serialize()}}
