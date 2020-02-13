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
