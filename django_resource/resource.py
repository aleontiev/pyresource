from .expression import execute
from .utils import as_dict, cached_property
from .store import Store


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
                    "is": "union",
                    "of": [
                        "null",
                        {"is": "array", "of": "string"},
                        {
                            "is": "object",
                            "of": {"is": "union", "of": ["null", "boolean", "object"]},
                        },
                    ],
                },
                "description": "A map from method name to access rule",
                "example": {
                    "get": True,
                    "clone.record": {
                        ".or": [{
                            "updated": {
                                "not.less.": "created"
                            }
                        }, {
                            "location.name": {
                                "not.in": ["USA", "UK"],
                            }
                        }]
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
            "bases": {
                "type": {"is": "array", "of": "?@resources"},
                "inverse": "children",
                "description": "The parent resource",
            },
            "features": {
                "type": "?object",
                "description": "All features supported by this resource",
                "example": {
                    "page": {"max": 100},
                    "with": True,
                    "sort": True,
                    "if": False,
                },
            },
            "before": {
                "type": "?object",
                "description": "Map of pre-event handlers",
                "example": {
                    "delete": {
                        ".check": {
                            '.or': [{
                                "can_delete": {
                                    "equals": True
                                }
                            }, {
                                ".request.is_superuser": True
                            }]
                        },
                    }
                },
            },
            "after": {
                "type": "?object",
                "description": "Map of post-event handlers",
                "example": {
                    "get.record": {".webhook": "https://webhooks.io/example/"},
                    "add": {".increment": "creator.num_created"},
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

    def _get_property(self, key):
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

    def add(self, key, value, index=None):
        return self._get_property(key).add_value(value, index=index)

    def get_property(self, key=None):
        return self._get_property(key).get_value(resolve=False, id=True)

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

    @cached_property
    def data(self):
        return Store(self)

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
                # shorthand where source field name is given as the only argument
                # in this case, use the store (e.g. DjangoStore) to determine the schema
                schema = self.data.get_schema_for(schema)

            resource_id = self.get_meta('id')
            id = f"{resource_id}.{key}"
            self._fields[key] = Field.make(
                parent=self,
                resource=resource_id,
                id=id,
                name=key,
                **schema
            )
        return self._fields[key]

    @classmethod
    def as_record(cls, **kwargs):
        id = cls.get_meta("id")
        fields = cls.get_fields()
        options = cls.get_meta()
        options["fields"] = ["{}.{}".format(id, key) for key in fields.keys()]
        for key, value in kwargs.items():
            options[key] = value
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
