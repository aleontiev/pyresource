class TypeValidationError(Exception):
    """Exception validating a data type"""
    pass


class QueryValidationError(Exception):
    """Exception validating a query input"""
    pass


class ExpressionValidationError(QueryValidationError):
    """Exception validating a query expression"""
    pass
