from .expression import execute
from .utils import as_dict


class Resource(object):
    class Schema:
        id = "resources"
        name = "resources"
        description = "A complex API type that can be acted upon with methods"
        space = "."
        can = ["read", "inspect"]
        parameters = None
        base = None
        features = None
        fields = {
            "id": {
                "primary": True,
                "type": "string",
                "description": "Identifies the resource within the server",
                "example": "resources",
            },
            "name": {
                "type": "string",
                "description": "Identifies the resource within its space",
                "example": "resources",
            },
            "singleton": {
                "type": "boolean",
                "default": False,
                "description": ("Whether or not the resource represents one record"),
            },
            "description": {
                "type": "?string",
                "description": "Explanation of the resource",
            },
            "space": {
                "type": "@spaces",
                "inverse": "resources",
                "description": "The space containing the resource",
            },
            "fields": {
                "type": {"is": "array", "of": "@fields"},
                "inverse": "resource",
                "description": "The fields that make up the resource",
            },
            "can": {
                "type": {
                    "is": "?union",
                    "of": [
                        {"is": "array", "of": "string"},
                        {
                            "is": "object",
                            "of": {"is": "union", "of": ["null", "boolean", "object"]},
                        },
                    ],
                },
                "description": "An map from method name to access rule",
                "example": {
                    "get": True,
                    "clone.record": {
                        "": "x | y",
                        "updated:gt:x:": "created",
                        "location.name:not.in:y": ["USA", "UK"],
                    },
                },
            },
            "parameters": {
                "type": {"is": "?object", "of": {"is": "object", "of": "type"}},
                "description": "An object of custom input keys",
                "example": {
                    "clone.record": {"remap": {"is": "object", "of": "string"}}
                },
            },
            "base": {
                "type": "?@resources",
                "inverse": "children",
                "description": "The parent resource",
            },
            "children": {
                "type": {"is": "array", "of": "@resources"},
                "inverse": "base",
                "description": "All resources that extend this one",
            },
            "features": {
                "type": "?object",
                "description": "All features supported by this resource",
                "example": {
                    "page": {"max_size": 100},
                    "with": True,
                    "sort": True,
                    "if": False,
                },
            },
            "on": {
                "type": "?object",
                "description": "Map of event handlers",
                "example": {
                    "get.record": {"url": "https://webhooks.io/example/"},
                    "add": {"increment": "creator.num_created"},
                },
            },
            "abstract": {"type": "boolean", "default": False},
        }

    def __repr__(self):
        return str(self)

    def __str__(self):
        id = self.get_id()
        return f"({self.__class__.__name__}: {id})"

    def __init__(self, **options):
        # make sure there is a schema and a name
        assert self.Schema.name is not None

        self._setup = False
        self._options = options
        self._fields = {}

    def __getattr__(self, key):
        if key.startswith("_"):
            return self.__dict__.get(key, None)

        return self.get_field(key).get_value()

    def __setattr__(self, key, value):
        if key.startswith("_"):
            return super(Resource, self).__setattr__(key, value)

        field = self.get_field(key)
        field.set_value(value)

    def _get(self, key):
        """Get field at given key (supporting.nested.paths)

        Raises:
            ValueError if key is not valid
        """
        if key is None:
            return self

        keys = [k for k in key.split(".") if k] if key else []
        value = self
        last = len(keys)
        if not last:
            this = str(self)
            raise ValueError(f"{key} is not a valid field of {this}")
        for i, key in enumerate(keys):
            is_last = i == last
            if key:
                field = value.get_field(key)
                if not is_last:
                    value = field.get_value()
        return field

    def add(self, value, key=None, index=None):
        return self._get(key).add_value(value, index=index)

    def get(self, key=None):
        return self._get(key).get_value(resolve=False, id=True)

    def get_option(self, key, default=None):
        if key in self._options:
            return self._options[key]
        else:
            if callable(default):
                # callable that takes self
                default = default(self)
            elif isinstance(default, dict):
                # expression that takes self
                default, _ = execute(default, self)
            return default

    @classmethod
    def get_fields(cls):
        return cls.Schema.fields

    def get_field(self, key):
        from .field import Field

        fields = self.get_fields()
        if key not in self._fields:
            if key not in fields:
                this = str(self)
                raise AttributeError(f"{key} is not a valid field of {this}")

            schema = fields[key]
            if not isinstance(schema, dict):
                # shorthand where type is given as the only argument
                schema = {"type": schema}
            id = "{0}.{1}".format(self.get_meta("id"), key)
            self._fields[key] = Field.make(resource=self, id=id, name=key, **schema)
        return self._fields[key]

    def get_record(self, key=None):
        if isinstance(key, Resource):
            # short-circuit and return key if already a resource
            return key
        if key in self._data:
            return self._data[key]
        return self._data.get(key)

    @classmethod
    def as_record(cls):
        name = cls.get_meta("name")
        fields = cls.get_fields()
        options = cls.get_meta()
        options["fields"] = ["{}.{}".format(name, key) for key in fields.keys()]
        return Resource(**options)

    def get_id_field(self):
        if getattr(self, "_id_field", None):
            return self._id_field

        for name, field in self.get_fields().items():
            if isinstance(field, dict) and field.get("primary", False):
                self._id_field = name
                return name

        raise ValueError(f"Resource {self.name} has no primary key")

    def get_id(self):
        if self.get_meta("singleton"):
            # singleton ID = name
            return self.get_meta("name")
        id_field = self.get_id_field()
        return (
            getattr(self, id_field)
            if id_field in self._fields
            else self.get_option(id_field)
        )

    @classmethod
    def get_meta(cls, key=None, default=None):
        if not key:
            return as_dict(cls.Schema)
        return getattr(cls.Schema, key, default)


def is_resolved(x):
    if isinstance(x, Resource):
        return True
    if isinstance(x, list) and all((isinstance(c, Resource) for c in x)):
        return True
    if isinstance(x, dict) and all((isinstance(c, Resource) for c in x.values())):
        return True
    return False
