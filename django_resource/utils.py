from django.core.templates import Template


def resolve_template(template, context):
    template = Template(template)
    return template.render(**context)
