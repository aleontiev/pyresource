from itertools import chain

from pyresource.executor import Executor
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


class MetaExecutor(Executor):

    def get_record(self, query, request=None, **context):
        return self._get_resource("record", query, request=request, **context)

    def get_field(self, query, request=None, **context):
        return self._get_resource("field", query, request=request, **context)

    def get_resource(self, query, request=None, **context):
        return self._get_resource("resource", query, request=request, **context)

    def _get_by_id(self, data, id, field='id'):
        for d in data:
            d_id = getattr(d, field)
            if d_id == id:
                return d
        raise NotFound()

    def _get_data(self, resource, fields, query, request=None, can=None, **context):
        server = query.server
        resource_id = resource.id
        record_id = query.state.get('id')
        if resource_id == 'server':
            return server
        elif resource_id == 'spaces':
            spaces = server.spaces
            return self._get_by_id(spaces, record_id, field='name') if record_id else spaces
        elif resource_id == 'resources':
            spaces = server.spaces
            resources = list(chain.from_iterable((space.resources for space in spaces)))
            return self._get_by_id(resources, record_id) if record_id else resources
        elif resource_id == 'fields':
            spaces = server.spaces
            resources = chain.from_iterable((space.resources for space in spaces))
            fields = list(chain.from_iterable((resource.fields for resource in resources)))
            return self._get_by_id(fields, record_id) if record_id else fields
        else:
            raise NotImplementedError()

    def _get_resource(
        self, endpoint, query, request=None, prefix=None, resource=None, **context
    ):
        resource = self._resource_from_query(query, resource)
        can = self._can(resource, f"get.{endpoint}", query, request)
        if not can:
            raise Forbidden()

        source = resource.source

        meta = {}

        fields = self._take_fields(
            resource, action="get", query=query, request=request,
        )

        record = self._get_data(
            resource, fields, query, request=request, can=can, **context
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
