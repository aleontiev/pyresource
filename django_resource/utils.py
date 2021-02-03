from django.template import Template, Context
from django.utils.functional import cached_property  # noqa


def resolve(template, context):
    template = Template(template)
    context = Context(context)
    return template.render(context)


def set_dict(target, template, value):
    parts = template.split(".") if isinstance(template, str) else template
    num_parts = len(parts)
    for i, part in enumerate(parts):
        if part not in target:
            target[part] = {}
        if i == num_parts - 1:
            target[part] = value
        else:
            target = target[part]


def get(template, context):
    if not template or not context:
        return None
    parts = template.split(".") if isinstance(template, str) else template
    part = parts[0]
    if isinstance(context, dict):
        next_context = context.get(part, None)
    else:
        next_context = getattr(context, part, None)

    if len(parts) == 1:
        return next_context
    else:
        return get(parts[1:], next_context)


def as_dict(obj):
    return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}


def merge(source, dest):
    for key, value in source.items():
        if isinstance(value, dict):
            node = dest.setdefault(key, {})
            merge(value, node)
        else:
            curr = dest.get(key)
            if not isinstance(curr, dict) or not isinstance(value, bool):
                dest[key] = value
            # else: merge a boolean and dict together as the dict

    return dest


def type_add_null(null, other):
    """Naybe add null to a JSONSChema type"""
    if not null:
        return other
    if isinstance(other, list):
        if "null" not in other:
            other.append("null")
        return other
    elif isinstance(other, dict):
        return {"anyOf": [{"type": "null"}, other]}
    elif isinstance(other, str):
        # string
        return ["null", other]
    else:
        raise ValueError(f"Bad type: {other}")


def coerce_query_value(value, singletons=True):
    """Try to coerce to boolean, null, integer, float"""
    if singletons:
        # coerce to singleton values: boolean/null

        lower = value.lower()
        if lower == "true":
            return True

        if lower == "false":
            return False

        if lower == "null":
            return None

    try:
        value = int(value)
    except ValueError:
        pass
    else:
        return value

    try:
        value = float(value)
    except ValueError:
        pass
    else:
        return value

    return value


def coerce_query_values(values, singletons=True):
    single = isinstance(values, list) and len(values) == 1
    values = [coerce_query_value(value, singletons) for value in values]
    return values[0] if single else values


def is_literal(key):
    if not isinstance(key, str):
        return True
    # for strings
    if key and key.startswith('"') or key.startswith("'") and key[0] == key[-1]:
        return True
    return False

def make_literal(value):
    if value is None:
        return None
    if isinstance(value, (bool, int, float, decimal.Decimal)):
        return value
    if isinstance(value, (list, tuple)):
        return [make_literal(v) for v in value]
    if isinstance(value, str):
        return f'"{value}"'

    raise ValueError(f'cannot make {value} into a literal')


def resource_to_django(key):
    if isinstance(key, (list, tuple)):
        return [resource_to_django(k) for k in key]

    desc = False
    if key.startswith('-'):
        desc = True
        key = key[1:]

    if key.startswith('.'):
        # this is an annotation and should not have any other "."
        assert key.count('.') == 1
        return f'-{key}' if desc else key
    key = key.replace('.', '__')
    return f'-{key}' if desc else key
