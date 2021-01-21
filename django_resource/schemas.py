from .version import version


class ResourceSchema:
    id = "resources"
    name = "resources"
    source = None
    description = "A complex API type composed of many fields"
    space = "."
    can = {"get": True, "inspect": True}
    parameters = None
    base = None
    features = None
    fields = {
        "id": {
            "primary": True,
            "type": "string",
            "description": "Identifies the resource within the server",
            "example": "resources",
            "default": {"concat": ["space.name", '"."', "name"]},
        },
        "source": {
            "type": "any",
            "description": "Null, string, or object",
            "example": {"source": "auth.user", "where": {"=": ["is_active", True]}},
        },
        "url": {
            "type": "string",
            "source": {"concat": ["space.url", "name", "'/'",]},
            "can": {"set": False},
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
            "type": ["null", "string"],
            "description": "Explanation of the resource",
        },
        "space": {
            "type": "@spaces",
            "inverse": "resources",
            "description": "The space containing the resource",
        },
        "fields": {
            "type": {"type": "array", "items": "@fields"},
            "inverse": "resource",
            "description": "The fields that make up the resource",
        },
        "can": {
            "type": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "array", "items": "string"},
                    {
                        "type": "object",
                        "additionalProperties": {"type": ["null", "boolean", "object"]},
                    },
                ]
            },
            "description": "A map from action name to access rule",
            "example": {
                "get": True,
                "clone.record": {
                    "or": [
                        {"not": {"<": ["updated", "created"]}},
                        {"not.in": {"location.name": ["'USA'", "'UK'"],}},
                    ]
                },
            },
        },
        "parameters": {
            "type": {"type": "object", "additionalProperties": {"type": "type"}},
            "description": "An object of custom input keys",
            "example": {"clone.record": {"remap": {"is": "object", "of": "string"}}},
        },
        "bases": {
            "type": {"type": "array", "items": "@resources"},
            "inverse": "children",
            "description": "The parent resource",
        },
        "features": {
            "type": ["null", "object"],
            "description": "All features supported by this resource",
            "example": {
                "page": {"max": 100},
                "show": True,
                "sort": True,
                "where": False,
            },
        },
        "before": {
            "type": ["null", "object"],
            "description": "Map of pre-event handlers",
            "example": {
                "delete": {
                    "verify": {
                        ".or": [
                            {".request.user.id": {".equals": "owner"}},
                            {".request.user.roles": {"contains": "superuser"}},
                        ]
                    },
                }
            },
        },
        "after": {
            "type": ["null", "object"],
            "description": "Map of post-event handlers",
            "example": {
                "get.record": {"webhook": "https://webhooks.io/example/"},
                "add": {"increment": "creator.num_created"},
            },
        },
        "abstract": {"type": "boolean", "default": False},
    }


class SpaceSchema:
    id = "spaces"
    name = "spaces"
    description = "spaces description"
    space = "."
    can = ["read", "inspect"]
    fields = {
        "server": {"type": "@server", "inverse": "spaces"},
        "url": {
            "type": "string",
            "source": {"concat": ["server.url", "name", "'/'"]},
            "can": {"set": False},
        },
        "name": {"type": "string", "primary": True},
        "resources": {
            "type": {"type": "array", "items": "@resources"},
            "inverse": "space",
            "default": [],
        },
    }


class ServerSchema:
    id = "server"
    source = None
    name = "server"
    singleton = True
    space = "."
    description = "server description"
    fields = {
        "version": {"type": "string", "default": version},
        "url": {"type": "string", "primary": True},
        "spaces": {
            "type": {"type": "array", "items": "@spaces"},
            "inverse": "server",
            "default": [],
        },
        "features": {
            "type": {
                "anyOf": [
                    {"type": "object"},
                    {"type": "array", "additionalProperties": {"type": "string"}},
                ]
            },
            "default": {
                "with": {"max_depth": 5},
                "where": {
                    "max_depth": 3,
                    "operators": [
                        "=",  # =
                        "!=",
                        "<",
                        "<=",
                        ">=",
                        ">",
                        "in",  # contains
                        "not.in",  # does not contain
                        "range",
                        "null",
                        "not.null",
                        "contains",
                        "matches",
                    ],
                },
                "page": {"max": 1000},
                "group": {
                    "operators": ["max", "min", "sum", "count", "average", "distinct"]
                },
                "sort": True,
                "inspect": True,
                "action": True,
            },
        },
        "types": {
            "type": {"type": "array", "items": "@types"},
            "default": [],
            "inverse": "server",
        },
    }


class FieldSchema:
    id = "fields"
    name = "fields"
    space = "."
    description = "Description of fields"
    fields = {
        "id": {"type": "string", "primary": True,},
        "resource": {"type": "@resources", "inverse": "fields"},
        "source": {"type": "any"},
        "inverse": {"type": ["null", "string"]},
        "name": {"type": "string"},
        "can": {
            "type": [
                {"type": "object",},
                {"type": "array", "items": {"type": "string"}},
            ]
        },
        "url": {
            "type": "string",
            "source": {"concat": ["resource.url", "name", "'/'",]},
            "can": {"set": False},
        },
        "description": {"type": ["null", "string"]},
        "example": {"type": "any"},
        "type": {"type": "type"},
        "unique": {"type": "boolean", "default": False},
        "lazy": {"type": "boolean", "default": False},
        "index": {"type": ["boolean", "string"], "default": False},
        "primary": {"type": "boolean", "default": False},
        "default": {"type": "any"},
    }
