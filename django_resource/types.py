from .resource import Resource
from decimal import Decimal
from .schemas import TypeSchema
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
    class Schema(TypeSchema):
        pass

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


