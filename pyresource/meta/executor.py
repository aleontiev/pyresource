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

    def _get_data(self, resource, fields, query, request=None, can=None, **context):
        server = query.server
        if resource.id == 'server':
            return server
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

        if resource.singleton:
            # get queryset and obtain first record
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
        else:
            records = self._get_data(
                resource,
                fields,
                query,
                count=count,
                request=request,
                can=can,
                **context,
            )
            if endpoint != "resource":
                # resource endpoint has many root-level records
                # field/record endpoints have one root-level record only
                records = records[0]
                if not records:
                    # no record
                    raise NotFound()
            data = self._serialize(
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
