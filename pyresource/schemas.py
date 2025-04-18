from .version import version


can_type = {
    "anyOf": [
        {"type": "null"},
        {"type": "array", "items": "string"},
        {
            "type": "object",
            "additionalProperties": {"type": ["null", "boolean", "object"]},
        },
    ]
}
can = {
    "type": can_type,
    "description": "A map from action name to access rule",
    "example": {
        "get": True,
        "set": {
            "<": ["updated", "created"]
        },
    },
}

class ResourceSchema:
    id = "resources"
    name = "resources"
    source = None
    description = "A complex API type composed of many fields"
    space = "."
    parameters = None
    features = None
    engine = "resource"
    fields = {
        "id": {
            "primary": True,
            "type": "string",
            "description": "Identifies the resource within the server",
            "default": {"concat": ["space.name", '"."', "name"]},
        },
        "source": {
            "type": "any",
            "description": "Null, string, or object describing the datasource",
        },
        "url": {
            "type": "string",
            "source": {"concat": ["space.url", "name", "'/'",]},
            "can": {"get": True},
        },
        "name": {
            "type": "string",
            "description": "Identifies the resource within its space",
        },
        "singleton": {
            "type": "boolean",
            "default": False,
            "description": "Whether or not the resource represents one record",
        },
        "description": {
            "type": ["null", "string"],
            "description": "Explanation of the resource",
        },
        "engine": {
            "type": "string",
            "default": ".globals.engine"
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
        "can": can,
        "parameters": {
            "type": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "object", "additionalProperties": {"type": "type"}}
                ]
            },
            "description": "An object of custom input keys",
        },
        "features": {
            "type": ["null", "object"],
            "description": "All features supported by this resource, with configuration",
            "example": {
                "page": {"size": 50, "max_size": 100},
                "take": True,
                "sort": True,
                "where": False,
            },
        },
        "labels": {
            "type": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "array", "items": "string"}
                ]
            },
            "description": "Optional set of string labels"
        },
        "label": {
            "type": ["string", "null"],
            "description": "Optional label"
        },
        "before": {
            "type": ["null", "object"],
            "description": "Map of pre-event handlers",
        },
        "after": {
            "type": ["null", "object"],
            "description": "Map of post-event handlers",
        },
        "abstract": {"type": "boolean", "default": False},
    }


class SpaceSchema:
    id = "spaces"
    name = "spaces"
    description = "spaces description"
    space = "."
    fields = {
        "server": {"type": "@server", "inverse": "spaces"},
        "url": {
            "type": "string",
            "source": {"concat": ["server.url", "name", "'/'"]},
            "can": {"get": True},
        },
        "name": {"type": "string", "primary": True},
        "can": can,
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
    source = None
    singleton = True
    space = "."
    description = "server description"
    fields = {
        "version": {"type": "string", "default": f'"{version}"'},
        "url": {"type": "string", "primary": True},
        "spaces": {
            "type": {"type": "array", "items": "@spaces"},
            "inverse": "server",
            "default": [],
        },
        "source": {"type": ["null", "string", "object"]},
        "can": can,
        "features": {
            "type": {
                "anyOf": [
                    {"type": "object"},
                    {"type": "array", "additionalProperties": {"type": "string"}},
                ]
            },
            "default": {
                "take": True,
                "where": True,
                "page": {"size": 50, "max_size": 100},
                "group": True,
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
        "id": {"type": "string", "primary": True},
        "resource": {"type": "@resources", "inverse": "fields"},
        "source": {"type": "any"},
        "inverse": {"type": ["null", "string"]},
        "name": {"type": "string"},
        "can": {
            "type": [
                {"type": "null"},
                {"type": "object",},
                {"type": "array", "items": {"type": "string"}},
            ]
        },
        "url": {
            "type": "string",
            "source": {"concat": ["resource.url", "name", "'/'",]},
            "can": {"get": True}
        },
        "options": {
            "type": {
                "anyOf": [{
                    "type": "null"
                }, {
                    "type": "array",
                    "items": {
                        "anyOf": [{
                            "type": "object",
                            "properties": {
                                "value": "any",
                                "can": can_type,
                                "label": "string"
                            },
                            "required": ["value"]
                        }, {
                            "type": ["string", "number"]
                        }]
                    }
                }]
            },
            "example": [{
                "value": 1,
                "label": "admin",
                "can": {"set": ".request.user.is_superuser"}
            }, {
                "value": 2,
                "label": "default",
            }]
        },
        "depends": {"type": ["null", "string", "object"]},
        "description": {"type": ["null", "string"]},
        "example": {"type": "any"},
        "type": {"type": "type"},
        "unique": {"type": "boolean", "default": False},
        "lazy": {"type": "boolean", "default": False},
        "index": {"type": ["boolean", "string"], "default": False},
        "primary": {"type": "boolean", "default": False},
        "default": {"type": "any"},
    }


class TypeSchema:
    id = "types"
    name = "types"
    space = "."
    fields = {
        "name": {"type": "string", "primary": True},
        "base": {"type": "@types", "inverse": "children"},
        "children": {
            "type": {
                "type": "array",
                "items": "@types"
            },
            "inverse": "base",
            "default": [],
        },
        "container": {"type": "boolean", "default": False},
        "server": {"type": "@server", "inverse": "types"},
    }


Schemas = {
    "server": ServerSchema,
    "spaces": SpaceSchema,
    "resources": ResourceSchema,
    "fields": FieldSchema,
    "types": TypeSchema,
}
