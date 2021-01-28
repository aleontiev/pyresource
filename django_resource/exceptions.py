class TypeValidationError(Exception):
    """Exception validating a data type"""
    pass


class QueryValidationError(Exception):
    """Exception validating a query input"""
    pass


class QueryExecutionError(Exception):
    """Exception executing a query"""
    pass


class ExpressionValidationError(QueryValidationError):
    """Exception validating a query expression"""
    pass


class SchemaResolverError(Exception):
    """Exception resolving schema data from the ORM"""
    pass

class ResourceMisconfigured(QueryExecutionError):
    """Exception caused by resource misconfiguration"""
    pass


class FieldMisconfigured(ResourceMisconfigured):
    """Exception caused by field misconfiguration"""
    pass


class FilterError(Exception):
    pass


class ExpressionError(Exception):
    pass


class SerializationError(Exception):
    pass


class RequestError(Exception):
    pass


class BadRequest(RequestError):
    """400 bad request"""
    pass


class Unauthorized(RequestError):
    """401 unauthorized"""
    pass


class Forbidden(RequestError):
    """403 forbidden"""
    pass


class NotFound(RequestError):
    """404 not found"""
    pass


class MethodNotAllowed(RequestError):
    """405 method not allowed"""
    pass


class RequestTimeout(RequestError):
    """408 request timeout"""
    pass


class Conflict(RequestError):
    """409 conflict"""
    pass


class InternalServerError(RequestError):
    """500 error"""
    pass
