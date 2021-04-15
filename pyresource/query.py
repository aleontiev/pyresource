import json
import base64
from collections import defaultdict
from urllib.parse import parse_qs
from .utils import (
    merge as _merge,
    cached_property,
    coerce_query_value,
    coerce_query_values,
)
from copy import deepcopy
from .exceptions import QueryValidationError, QueryExecutionError
from .features import (
    get_feature,
    get_feature_separator,
    get_take_fields,
    get_sort_fields,
    NestedFeature,
    ROOT_FEATURES,
    QUERY,
    WHERE,
    TAKE,
    SORT,
)
from .boolean import WhereQueryMixin


class Query(WhereQueryMixin):
    # methods
    def __init__(self, state=None, server=None):
        """
        Arguments:
            state: internal query representation
        """
        self._state = state or {}
        self.server = server

    def __call__(self, *args, **kwargs):
        return self.from_querystring(*args, server=self.server, state=self.state)

    def add(self, id=None, field=None, **context):
        return self._call("add", id=id, field=field, **context)

    def set(self, id=None, field=None, **context):
        return self._call("set", id=id, field=field, **context)

    def get(self, id=None, field=None, **context):
        return self._call("get", id=id, field=field, **context)

    def edit(self, id=None, field=None, **context):
        return self._call("edit", id=id, field=field, **context)

    def delete(self, id=None, field=None, **context):
        return self._call("delete", id=id, field=field, **context)

    def options(self, id=None, field=None, **context):
        return self._call("options", id=id, field=field, **context)

    def explain(self, id=None, field=None, **context):
        return self._call("explain", id=id, field=field, **context)

    def encode(self):
        return base64.b64encode(json.dumps(self.state).encode('utf-8')).decode()

    @cached_property
    def executor(self):
        return self.server.get_executor(self)

    def execute(self, request=None, **context):
        executor = self.executor
        if not executor:
            raise QueryExecutionError(f"Query cannot execute without executor")
        action_name = self.state.get("action", "get")

        if "action" not in self.state:
            # add default action "get" into state
            self.state["action"] = action_name

        action = getattr(executor, action_name, None)
        if not action:
            raise QueryValidationError(f'Invalid action "{action_name}"')
        return action(self, request=request, **context)

    @property
    def state(self):
        return self._state

    def get_state(self, level=None):
        """Get state at a particular level

        If level is None, the root state will be returned
        Otherwise, the level is used as a key to traverse the state

        For example, if state = {"take": {"users": {"take": {"groups": True}}}
        and level = "users", result = {"take": {"groups": True}}
        and level = "users.groups", result = True
        """
        state = self.state
        if not level:
            return state
        parts = level.split(".") if isinstance(level, str) else level
        for index, part in enumerate(parts):
            if "take" not in state:
                raise QueryValidationError(
                    f'Invalid level: "{level}" at part "{part}" ({index})'
                )
            take = state["take"]
            if part not in take:
                raise QueryValidationError(
                    f'Invalid level: "{level}" at part "{part}" ({index})'
                )

            state = take[part]
        return state

    # features

    def data(self, data):
        return self._update({"data": data})

    def parameters(self, args=None, copy=True, **kwargs):
        return self._update({"parameters": kwargs}, merge=True, copy=copy)

    def id(self, name):
        return self._update({"id": name})

    def field(self, name):
        return self._update({"field": name})

    def space(self, name):
        return self._update({"space": name})

    def resource(self, name):
        return self._update({"resource": name})

    def action(self, name):
        return self._update({"action": name})

    @property
    def take(self):
        return NestedFeature(self, "take")

    @property
    def page(self):
        return NestedFeature(self, "page")

    @property
    def sort(self):
        return NestedFeature(self, "sort")

    @property
    def group(self):
        return NestedFeature(self, "group")

    def inspect(self, args=None, copy=True, **kwargs):
        """
        Example:
            .inspect(resource=True)
        """
        if args:
            kwargs = args

        return self._update({"inspect": kwargs}, copy=copy, merge=True)

    def _page(self, level, args=None, copy=True, **kwargs):
        """
        Example:
            .page('abcdef123a==', size=10)
        """
        if args:
            # cursor arg
            if isinstance(args, list):
                args = args[0]
            kwargs["after"] = args

        return self._update({"page": kwargs}, copy=copy, level=level, merge=True)

    def _take(self, level, *args, copy=True):
        kwargs = {}
        for arg in args:
            show = True
            if arg.startswith("-"):
                arg = arg[1:]
                show = False
            kwargs[arg] = show
        return self._update({"take": kwargs}, copy=copy, level=level, merge=True)

    def _call(self, action, id=None, field=None, **context):
        if self.state.get("action") != action:
            return getattr(self.action(action), action)(
                id=id, field=field, **context
            )

        if id or field:
            # redirect back through copy
            args = {}
            if id:
                args["id"] = id
            if field:
                args["field"] = field
            return getattr(self._update(args), action)(**context)

        return self.execute(**context)

    def _sort(self, level, *args, copy=True):
        """
        Example:
            .sort("name", "-created")
        """
        return self._update({"sort": list(args)}, copy=copy, level=level)

    def _group(self, level, args=None, copy=True, **kwargs):
        """
        Example:
            .group({"count": {"count": "id"})
        """
        if args:
            kwargs = args

        return self._update({"group": kwargs}, copy=copy, level=level, merge=True)

    def __str__(self):
        return str(self.state)

    def clone(self):
        return self._update()

    def _update(self, args=None, level=None, merge=False, copy=True, **kwargs):
        if args:
            kwargs = args

        state = None
        if copy:
            state = deepcopy(self.state)
        else:
            state = self.state

        sub = state
        # adjust substate at particular level
        # default: adjust root level
        take = "take"
        if level:
            for part in level.split("."):
                if take not in sub:
                    sub[take] = {}

                fields = sub[take]
                try:
                    new_sub = fields[part]
                except KeyError:
                    fields[part] = {}
                    sub = fields[part]
                else:
                    if isinstance(new_sub, bool):
                        fields[part] = {}
                        sub = fields[part]
                    else:
                        sub = new_sub

        for key, value in kwargs.items():
            if merge and isinstance(value, dict) and sub.get(key):
                # deep merge
                _merge(value, sub[key])
            else:
                # shallow merge, assign the state
                sub[key] = value

        if copy:
            return Query(state=state, server=self.server)
        else:
            return self

    def __getitem__(self, key):
        return self._state[key]

    def get_subquery(self, level=None):
        state = self.state
        substate = self.get_state(level)
        last_level = level.split('.')[-1] if level else None
        for feature in ROOT_FEATURES:
            if feature in state:
                substate[feature] = state[feature]

        # resource-bound subqueries are resource-bound
        if last_level and not state.get('resource'):
            if state.get('space'):
                # space-bound query, subquery becomes resource-bound
                substate['resource'] = last_level
            else:
                # server-bound query, subquery becomes space-bound
                substate['space'] = last_level

        return Query(state=substate, server=self.server)

    @classmethod
    def _build_update(cls, parts, key, value):
        update = {}
        num_parts = len(parts)
        if not key:
            update = value
        elif num_parts:
            update[key] = {}
            current = update[key]
            for i, part in enumerate(parts):
                if i != num_parts - 1:
                    current = current[part] = {}
                else:
                    current[part] = value

        else:
            update[key] = value
        return update

    @classmethod
    def decode_state(cls, state):
        try:
            return json.loads(base64.b64decode(state))
        except Exception:
            return None

    @classmethod
    def from_querystring(cls, querystring, **kwargs):
        state = cls.decode_state(querystring)
        if state is not None:
            # querystring is encoded state
            kwargs['state'] = state
            return cls(**kwargs)

        result = cls(**kwargs)
        state = kwargs.get("state")

        type = "server"
        if "resource" in state:
            type = "resource"
        elif "space" in state:
            type = "space"

        remainder = None
        space = resource = field = id = None
        parts = querystring.split("?")
        if len(parts) <= 2:
            resource_parts = parts[0]
            remainder = parts[1] if len(parts) == 2 else None
            resource_parts = [r for r in resource_parts.split("/") if r]
            update = {}
            len_resource = len(resource_parts)
            if len_resource == 1:
                if type == "server":
                    space = resource_parts[0]
                elif type == "space":
                    resource = resource_parts[0]
                else:
                    field = resource_parts[0]
            elif len_resource == 2:
                # either resource/id or space/resource or id/field
                if type == "server":
                    space, resource = resource_parts
                elif type == "space":
                    resource, id = resource_parts
                else:
                    id, field = resource_parts
            elif len_resource == 3:
                if type == "space":
                    resource, id, field = resource_parts
                elif type == "server":
                    space, resource, id = resource_parts
                else:
                    raise ValueError(f"Invalid querystring: {querystring}")
            elif len_resource == 4:
                if type == "server":
                    space, resource, id, field = resource_parts
                else:
                    raise ValueError(f"Invalid querystring: {querystring}")
            elif len_resource > 5:
                raise ValueError(f"Invalid querystring: {querystring}")

            if space is not None:
                update["space"] = space
            if resource is not None:
                update["resource"] = resource
            if id is not None:
                update["id"] = id
            if field is not None:
                update["field"] = field
            if update:
                result._update(update, copy=False)
        else:
            raise ValueError(f"Invalid querystring: {querystring}")

        if remainder:
            query = parse_qs(remainder)
        else:
            query = {}

        if QUERY in query:
            query = query[QUERY]
            if isinstance(query, list):
                query = query[0]
            state = cls.decode_state(query)
            if state is not None:
                # ?query=encoded-query
                kwargs['state'] = state
                return cls(**kwargs)
            else:
                raise ValueError(f'Invalid query: {query}')

        where = defaultdict(list)  # level -> [args]
        for key, value in query.items():
            feature = get_feature(key)
            separator = get_feature_separator(feature)

            # determine level
            parts = key.split(separator)
            feature_part = parts[0]

            level = None
            if "." in feature_part:
                level = ".".join(feature_part.split(".")[1:])
                if not level:
                    level = None

            parts = parts[1:]

            # handle WHERE separately because of special expression parsing
            # that can join together multiple conditions
            if feature == WHERE:
                parts.append(value)
                where[level].append(parts)
                continue

            # coerce value based on feature name
            update_key = feature
            if feature == TAKE:
                value = get_take_fields(value)
            elif feature == SORT:
                value = get_sort_fields(value)
            else:
                value = coerce_query_values(value)

            if update_key == "page" and not parts:
                # default key for page = cursor
                parts = ["cursor"]

            update = cls._build_update(parts, update_key, value)
            result._update(update, level=level, merge=feature != SORT, copy=False)
        if where:
            # WhereQueryMixin
            # special handling
            cls.update_where(result, where)
        return result

    @property
    def where(self):
        return NestedFeature(self, "where")

    def _where(self, level, query, copy=True):
        """
        Example:
            .where({
                'or': [
                    {'contains': ['users.location.name', '"New York"']},
                    {'not': {'in': ['users', [1, 2]]}}
                ]
            })
        """
        return self._update({"where": query}, copy=copy, level=level)
