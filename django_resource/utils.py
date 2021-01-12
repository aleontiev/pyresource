from django.template import Template, Context
from django.utils.functional import cached_property  # noqa


def resolve(template, context):
    template = Template(template)
    context = Context(context)
    return template.render(context)


def get(template, context):
    if not template or not context:
        return None
    parts = template.split('.') if isinstance(template, str) else template
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
    return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}


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
