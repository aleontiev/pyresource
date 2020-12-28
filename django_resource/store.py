from .utils import cached_property
from .query import Query


class SchemaResolver(object):
    def __init__(self, resource):
        self.resource = resource

    def get_schema(self, source):
        schema = {"source": source}
        model = getattr(self, "model", None)

        if not model:
            return schema

        schema["type"] = self.get_type(source, model)
        schema["default"] = self.get_default(source, model)
        schema["choices"] = self.get_choices(source, model)
        schema["description"] = self.get_description(source, model)
        schema["unique"] = self.get_unique(source, model)
        schema["index"] = self.get_index(source, model)
        return schema


class DjangoSchemaResolver(SchemaResolver):
    @classmethod
    def get_type(self, source, model):
        pass

    @classmethod
    def get_choices(self, source, model):
        pass

    @classmethod
    def get_description(self):
        pass

    @cached_property
    def model(self):
        return self.get_model()

    def get_model(self):
        if self.resource.source:
            # resolve model at this time if provided, throwing an error
            # if it does not exist or if Django is not imported
            from django.apps import apps

            app_label, model_name = self.source.split(".")
            return apps.get_model(app_label=app_label, model_name=model_name)
        else:
            return None


class Executor(object):
    """Executes Query, returns dict response"""

    def __init__(self, resource, **kwargs):
        self.resource = resource

    def get(self, query, identity=None):
        """
            Arguments:
                query: query dict
                identity: user identity dict
        """
        pass


class DjangoExecutor(Executor):
    pass


class Store(object):
    def __init__(self, resource):
        if resource.__class__.__name__ == 'Space':
            self.space = resource
            self.resource = None
        else:
            self.resource = resource
            self.space = resource.space

        self.resolver = self.get_resolver(self.space)
        self.executor = self.get_executor(self.space)

    def get_executor(self, space):
        return DjangoExecutor(space)

    @property
    def query(self):
        return self.get_query()

    def get_query(self, querystring=None):
        initial = {
            ".space": self.space.name
        }
        if self.resource:
            initial[".resource"] = self.resource.name

        executor = self.executor
        if querystring:
            return Query.from_querystring(
                querystring,
                state=initial,
                executor=executor
            )
        else:
            return Query(
                state=initial,
                executor=executor
            )

    def get_resolver(self, space):
        return DjangoSchemaResolver(space)

    def get_schema(self, source):
        return self.resolver.get_schema(source)
