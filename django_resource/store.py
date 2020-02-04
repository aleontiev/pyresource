from .utils import cached_property, merge as _merge
import copy


class NestedFeature(object):
    def __init__(self, query, name, level=None):
        self.query = query
        self.name = name
        self.level = level

    def __getattr__(self, key):
        # adjust level
        if self.level:
            level = "{}.{}".format(self.level, key)
        else:
            level = key
        return NestedFeature(query=self.query, name=self.name, level=level)

    def __call__(self, *args, **kwargs):
        args.insert(0, self.level)
        # call back to query with arguments
        getattr(self.query, "_{}".format(self.name))(*args, **kwargs)


class Query(object):
    # methods
    def __init__(self, state=None):
        """
        Arguments:
            state:
                example: {
                    ".page": {
                        "key": "123abcdef===",
                        "size": 30
                    },
                    ".sort": ["name", "-created"],
                    "*": True,
                    "body": False,
                    "group": {
                        ".where": {
                            ".or": [
                                {"name": {"contains": "abc"}},
                                {"id": {"equals": "1"}}
                            ]
                        },
                        "id": True,
                        "name": True
                    }
                }

                ...would be the state running:

                query.select('*', '-body')
                .sort('name', '-created')
                .select.group('id', 'name')
                .where.group({
                    '.and': [{
                            "active": true,
                        },
                            ".or": [
                                {"name": {"contains": "abc"},
                                {"name": "John Smith}
                            ]
                        }
                    ]
                })
                .page(key='123abcdef===', size=30)

                or:

                ?select=*,-body
                &sort=name,-created
                &select.group=id,name
                &where.group:active:equals:1=true
                &where.group:name:contains:2=abc
                &where.group:name:contains:3=John+Smith
                &where.group=1(2,3)
        """

        self._state = state or {}

    def add(self):
        raise NotImplementedError()

    def set(self):
        raise NotImplementedError()

    def get(self, record=None, field=None):
        if record or field:
            # redirect back through copy
            args = {}
            if record:
                args['.record'] = record
            if field:
                args['.field'] = field
            return self._copy(args).get()

        # execute get query
        raise NotImplementedError()

    def edit(self):
        raise NotImplementedError()

    def delete(self):
        raise NotImplementedError()

    def options(self):
        raise NotImplementedError()

    def call(self, **kwargs):
        method = self._state.get('.method', 'get')
        method = getattr(self, method)
        return method(**kwargs)

    # features

    def body(self, body):
        return self._copy({".body": body})

    def record(self, name):
        return self._copy({".record": name})

    def field(self, name):
        return self._copy({".field": name})

    def method(self, name):
        return self._copy({".method": name})

    @property
    def select(self):
        return NestedFeature(self, "select")

    @property
    def where(self):
        return NestedFeature(self, "where")

    @property
    def sort(self):
        return NestedFeature(self, "sort")

    @property
    def group(self):
        return NestedFeature(self, "group")

    def inspect(self, args=None, **kwargs):
        """
        Example:
            .inspect(resource=True)
        """
        if args:
            kwargs = args.items()

        return self._copy({".inspect": kwargs})

    def page(self, args=None, **kwargs):
        """
        Example:
            .page(key='abcdef123a==')
        """
        if args:
            kwargs = args.items()

        return self._copy({".page": kwargs})

    def _select(self, level, *args):
        pass

    def _where(self, level, query):
        """
        Example:
            .where({
                '.or': [
                    {'users.location.name': {'contains': 'New York'}},
                    {'.not': {'users.in': [1, 2]}}
                ]
            })
        """
        return self._copy({".where": query}, level=level)

    def _sort(self, level, *args):
        """
        Example:
            .sort("name", "-created")
        """
        return self._copy({".sort": args}, level=level)

    def _group(self, level, args=None, **kwargs):
        """
        Example:
            .group(count={"count": "id"})
        """
        if args:
            kwargs = args.items()

        return self._copy({".group": kwargs}, level=level, merge=True)

    def _copy(self, args=None, level=None, merge=False, **kwargs):
        if args:
            kwargs = args.items()

        sub = state = copy.deepcopy(self._state)

        # adjust substate at particular level
        # default: adjust root level
        if level:
            for part in level.split("."):
                try:
                    sub = sub.get(part)
                except KeyError:
                    sub = sub[part] = {}

        for key, value in kwargs.items():
            if merge and isinstance(value, dict) and sub[key]:
                # deep merge
                _merge(value, sub[key])
            else:
                # shallow merge, assign the state
                sub[key] = value

        return self.from_dict(state)

    def __getitem__(self, key):
        return self._state[key]

    @classmethod
    def from_dict(cls, value):
        return cls(state=value)

    @classmethod
    def from_querystring(cls, value):
        pass


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


class Store(Query):
    def __init__(self, resource, **kwargs):
        self.resource = resource
        self.resolver = self.get_resolver(resource)
        super(Store, self).__init__(**kwargs)

    def get_resolver(self, resource):
        return DjangoSchemaResolver(resource)

    def get_schema(self, source):
        return self.resolver.get_schema(source)
