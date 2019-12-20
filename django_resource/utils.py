from django.template import Template, Context
from django.utils.functional import cached_property  # noqa


def resolve_template(template, context):
    template = Template(template)
    context = Context(context)
    return template.render(context)


def as_dict(obj):
    return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
