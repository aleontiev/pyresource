import re
from .utils import resolve, get


def resolve_expression(expression, context):
    while isinstance(expression, dict):
        expression, resolved = execute(expression, context)
        if not resolved:
            break
    return expression


def get_expression(expression, context):
    if not expression:
        return expression

    expression = resolve(expression, context)
    return get(expression, context)


def format_expression(expression, context):
    if not expression:
        return expression

    expression = resolve_expression(expression, context)

    if isinstance(expression, dict):
        return {
            format_expression(k, context): format_expression(v, context)
            for k, v in expression.items()
        }
    elif isinstance(expression, list):
        return [format_expression(v) for v in expression]
    else:
        expression = re.sub(r"{{\s*\.", "{{ self.", expression)
        return resolve(expression, {"self": context})


def value_expression(expression, context):
    return expression


methods = {
    "get": get_expression,
    "format": format_expression,
    "value": value_expression,
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
