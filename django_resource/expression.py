import re
from .utils import resolve, get, is_literal, unliteral


def get_expression(expression, context):
    if not expression:
        return expression

    if is_literal(expression):
        return unliteral(expression)

    if expression.startswith('.'):
        # .request.user -> request.user
        expression = expression[1:]
    elif 'fields' in context and not expression.startswith('fields.'):
        # name -> fields.name
        expression = f'fields.{expression}'

    expression = resolve(expression, context)
    return get(expression, context)


def join_expression(expression, context):
    if not expression:
        return expression

    separator = None
    if isinstance(expression, dict):
        # {"join": {"values": ["a", "b"], "separator": "/"}}
        values = expression.get('values')
        separator = expression.get('separator', ' ')
        values = [get_expression(v, context) for v in values]
    elif isinstance(expression, list):
        # {"join": ["a", "b"]}
        separator = ''
        values = [get_expression(v, context) for v in expression]
    elif isinstance(expression, str):
        # {"join": "a"}
        separator = ' '
        values = get_expression(expression, context)
        if not isinstance(values, list):
            raise ValueError(f'join expecting {values} to be list')
    else:
        raise ValueError(f'expression is not supported: {expression}')

    return separator.join([v for v in values if v])


def true_expression(expression, context):
    if isinstance(expression, str):
        expression = get_expression(expression, context)

    return bool(expression)


def false_expression(expression, context):
    return not true_expression(expression, context)


def value_expression(expression, context):
    return expression


methods = {
    "true": true_expression,
    "false": false_expression,
    "get": get_expression,
    "join": join_expression,
    "concat": join_expression
}


def execute(expression, context):
    if not expression:
        return expression, False

    if isinstance(expression, dict):
        keys = list(expression.keys())
        num_keys = len(keys)
        if num_keys != 1:
            return expression, False

        method = keys[0]
        if method.startswith("."):
            method = method[1:]
        args = expression[method]
        if method in methods:
            return methods[method](args, context), True
        else:
            # pass through
            return expression, False
    if isinstance(expression, str):
        method = "get"
        return methods[method](expression, context), True
