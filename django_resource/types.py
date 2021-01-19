from .resource import Resource
from decimal import Decimal
from .type_utils import (
    is_container,
    is_link,
    is_list,
    get_link,
    get_split_types,
    get_type_name,
    get_type_property,
    get_type_names,
    validate
)

class Type(Resource):
    class Schema:
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

    @classmethod
    def get_base_type(cls, name, server=None):
        kwargs = {
            "name": name,
            "base": "any",
            "container": is_container(name)
        }
        if server:
            kwargs["server"] = server
        return cls(**kwargs)


