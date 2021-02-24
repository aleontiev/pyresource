import re
from .utils import resolve, get, is_literal, unliteral


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


def not_expression(expression, context):
    if not expression:
        raise ValueError(f"not: expecting an argument")

    if isinstance(expression, list):
        size = len(expression)
        if size != 1:
            raise ValueError(f"not: expecting a list of size 1, not {size}")

        expression = expression[0]

    expression = execute(expression, context)
    return not bool(expression)


def and_expression(expression, context):
    if not isinstance(expression, list) or not expression:
        raise ValueError(f"and: list arguments expected, got {expression}")

    expressions = expression
    for expression in expressions:
        value = execute(expression, context)
        if not bool(value):
            return False
    return True


def get_expression(expression, context):
    if expression.startswith('.'):
        # .request.user -> request.user
        expression = expression[1:]
    elif 'fields' in context and not expression.startswith('fields.'):
        # name -> fields.name
        expression = f'fields.{expression}'

    return get(expression, context)


def join_expression(expression, context):
    separator = None
    if isinstance(expression, dict):
        # {"join": {"values": ["a", "b"], "separator": "/"}}
        values = expression.get('values')
        separator = expression.get('separator', ' ')
        values = [execute(v, context) for v in values]
    elif isinstance(expression, list):
        # {"join": ["a", "b"]}
        separator = ''
        values = [execute(v, context) for v in expression]
    elif isinstance(expression, str):
        # {"join": "a"}
        separator = ' '
        values = execute(expression, context)
        if not isinstance(values, list):
            raise ValueError(f'join expecting {values} to be list')
    else:
        raise ValueError(f'join: expression is not supported: {expression}')

    return separator.join([v for v in values if v])


def true_expression(expression, context):
    expression, _ = execute(expression, context)
    return bool(expression)


def false_expression(expression, context):
    return not true_expression(expression, context)


def object_expression(expression, context):
    return {
        key: execute(value, context) for key, value in expression.items()
    }


def literal_expression(expression, context):
    return expression


methods = {
    "true": true_expression,
    "false": false_expression,
    "get": get_expression,
    "join": join_expression,
    "concat": join_expression,
    "or": or_expression,
    "and": and_expression,
    "not": not_expression,
    "object": object_expression,
    "literal": literal_expression
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
