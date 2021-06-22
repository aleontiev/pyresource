from itertools import chain

from pyresource.executor import Executor
from pyresource.utils import reversor, get
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
from pyresource.conf import settings
from pyresource.expression import execute


class MetaExecutor(Executor):

    def get_record(self, query, request=None, **context):
        return self._get_resource("record", query, request=request, **context)

    def get_field(self, query, request=None, **context):
        return self._get_resource("field", query, request=request, **context)

    def get_resource(self, query, request=None, **context):
        return self._get_resource("resource", query, request=request, **context)

    def _get_by_id(self, data, id, field='id'):
        for item in data:
            item_id = getattr(item, field)
            if item_id == id:
                return item
        raise NotFound()

    def _item_match(self, where, item, request=None, **context):
        ctx = {}
        ctx['request'] = request
        ctx['fields'] = item
        return execute(where, ctx)

    def _item_sort(self, sort, item):
        return tuple(
            reversor(get(s[1:], item)) if s[0] == '-' else get(s, item)
            for s in sort
        )

    def _group(self, group, data):
        return data

    def _filter(self, query, resource, data, request=None, can=None, **context):
        # apply where/sort/group
        where = query.state.get('where')
        sort = query.state.get('sort')
        group = query.state.get('group')
        if where:
            data = [item for item in data if self._item_match(where, item, request=request, **context)]
        if sort:
            data.sort(key=lambda item: self._item_sort(sort, item))
        if group:
            data = self._group(group, data)
        return data

    def _get_data(self, query, resource, fields, request=None, can=None, **context):
        server = query.server
        resource_id = resource.id
        record_id = query.state.get('id')
        id_field = 'id'
        if resource_id == 'server':
            # singleton, no filtering possible
            return server
        # TODO: support filter (where), ordering (sort), aggregation (group) in this space
        # probably no need to support pagination
        elif resource_id == 'spaces':
            data = server.spaces
            id_field = 'name'
        elif resource_id == 'resources':
            spaces = server.spaces
            data = list(chain.from_iterable((space.resources for space in spaces)))
        elif resource_id == 'fields':
            spaces = server.spaces
            resources = chain.from_iterable((space.resources for space in spaces))
            data = list(chain.from_iterable((resource.fields for resource in resources)))
        else:
            raise NotImplementedError()

        return self._get_by_id(data, record_id, field=id_field) if record_id else self._filter(
            query,
            resource,
            data,
            request=request,
            can=can,
            **context
        )

    def _get_resource(
        self, endpoint, query, request=None, prefix=None, resource=None, **context
    ):
        resource = self._resource_from_query(query, resource)

        if resource.id == 'server':
            print(query.state)
        if resource.id == 'server' and query.state.get('parameters', {}).get('all'):
            # shorthand for take all
            query._take(None, '*', copy=False)
            query._take('spaces', '*', copy=False)
            query._take('spaces.resources', '*', copy=False)
            query._take('spaces.resources.fields', '*', copy=False)

        can = self._can(resource, f"get.{endpoint}", query, request)
        if not can:
            raise Forbidden()

        source = resource.source

        meta = {}

        fields = self._take_fields(
            resource, action="get", query=query, request=request,
        )

        record = self._get_data(
            query, resource, fields, request=request, can=can, **context
        )
        data = self._serialize(
            resource,
            fields,
            query=query,
            request=request,
            record=record,
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
