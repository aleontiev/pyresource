import re
from .utils import resolve, get, is_literal, unliteral


def object_expression(expression, context):
    return {key: execute(value, context) for key, value in expression.items()}


def literal_expression(expression, context):
    """return expression as-is"""
    return expression


def or_expression(expression, context):
    """or with short-circuit"""
    if not isinstance(expression, list) or not expression:
        raise ValueError(f"or: list arguments expected, got {expression}")

    expressions = expression
    for expression in expressions:
        value = execute(expression, context)
        if bool(value):
            return True
    return False


def and_expression(expression, context):
    """and with short-circuit execution"""
    if not isinstance(expression, list) or not expression:
        raise ValueError(f"and: list arguments expected, got {expression}")

    expressions = expression
    for expression in expressions:
        value = execute(expression, context)
        if not bool(value):
            return False
    return True


def get_expression(expression, context):
    """string getter"""
    if expression.startswith("."):
        # .request.user -> request.user
        expression = expression[1:]
    elif "fields" in context and not expression.startswith("fields."):
        # name -> fields.name
        expression = f"fields.{expression}"

    return get(expression, context)


def join_expression(expression, context):
    """string joiner, multiple signatures"""
    separator = None
    if isinstance(expression, dict):
        # {"join": {"values": ["a", "b"], "separator": "/"}}
        values = expression.get("values")
        separator = expression.get("separator", " ")
        values = [execute(v, context) for v in values]
    elif isinstance(expression, list):
        # {"join": ["a", "b"]}
        separator = ""
        values = [execute(v, context) for v in expression]
    elif isinstance(expression, str):
        # {"join": "a"}
        separator = " "
        values = execute(expression, context)
        if not isinstance(values, list):
            raise ValueError(f"join expecting {values} to be list")
    else:
        raise ValueError(f"join: expression is not supported: {expression}")

    return separator.join([v for v in values if v])


def make_unary_expression(final):
    def inner(expression, context):
        if not expression:
            raise ValueError(f"expecting an argument")

        if isinstance(expression, list):
            size = len(expression)
            if size != 1:
                raise ValueError(f"expecting exactly one argument, not {size}")

        expression = expression[0]
        left = execute(expression[0], context)
        return final(left)
    return inner


def make_binary_expression(final):
    def inner(expression, context):
        assert len(expression) == 2
        left = execute(expression[0], context)
        right = execute(expression[1], context)
        return final(left, right)
    return inner


def make_list_expression(final):
    def inner(expression, context):
        expression = [execute(expr, context) for expr in expression]
        return final(*expression)
    return inner


def negate(expression):
    def negated(expression, context):
        return not execute(expression, context)
    return negated


count = make_unary_expression(lambda x: len(x))
null = make_unary_expression(lambda x: x is None)
min_expression = make_list_expression(lambda *args: min(*args))
max_expression = make_list_expression(lambda *args: max(*args))
icontains_expression = make_binary_expression(
    lambda left, right: right.lower() in left.lower()
)
contains_expression = make_binary_expression(lambda left, right: right in left)
in_expression = make_binary_expression(lambda left, right: left in right)
less_than = make_binary_expression(lambda left, right: left < right)
greater_than = make_binary_expression(lambda left, right: left > right)
equals_expression = make_list_expression(lambda *args: len(args) == args.count(args[0]))
true_expression = make_unary_expression(lambda left: bool(left))

not_null = negate(null)
less_than_or_equal = negate(greater_than)
greater_than_or_equal = negate(less_than)
not_in = negate(in_expression)
not_equals = negate(equals_expression)
not_contains = negate(contains_expression)
false_expression = negate(true_expression)



methods = {
    "true": true_expression,
    "false": false_expression,
    "not": false_expression,
    "get": get_expression,
    "join": join_expression,
    "concat": join_expression,
    "or": or_expression,
    "and": and_expression,
    "object": object_expression,
    "literal": literal_expression,
    "in": in_expression,
    "-in": not_in,
    "not.in": not_in,
    "min": min_expression,
    "max": max_expression,
    "contains": contains_expression,
    "not.contains": not_contains,
    "-contains": not_contains,
    "less": less_than,
    "greater": greater_than,
    "<": less_than,
    "lt": less_than,
    "lte": less_than_or_equal,
    ">": greater_than,
    "gt": greater_than,
    "gte": greater_than_or_equal,
    "<=": less_than_or_equal,
    ">=": greater_than_or_equal,
    "=": equals_expression,
    "is": equals_expression,
    "eq": equals_expression,
    "equal": equals_expression,
    "equals": equals_expression,
    "ne": not_equals,
    "neq": not_equals,
    "!=": not_equals,
    "not.equal": not_equals,
    'is.null': null,
    'null': null,
    '-null': not_null,
    'not.null': not_null,
    'length': count,
    'count': count
}


def execute(expression, context):
    if is_literal(expression):
        # True, None, 1.1, 'test'
        return unliteral(expression)

    if not expression:
        # [], "", {}
        return expression

    if isinstance(expression, dict):
        keys = list(expression.keys())
        num_keys = len(keys)
        method = keys[0]
        if method in methods:
            # a known expression method
            return methods[method](expression[method], context)
        elif num_keys == 1:
            raise ValueError(f"execute: unknown expression operator: {method}")
        # multiple keys, use object expression
        return object_expression(expression, context)

    if isinstance(expression, str):
        # dotted.path
        method = "get"
        return methods[method](expression, context)
