from pyresource.exceptions import TypeValidationError

types = [
    "any",
    "null",
    "string",
    "number",
    "boolean",
    "type",
    "link",
    "union",
    "map",
    "tuple",
    "object",
    "option",
    "array"
]


def is_nullable(T):
    """Return true if T is a null type or list with none type"""
    name = get_type_name(T)
    names = get_type_names(T)
    if name in {'null', 'any'} or names and 'null' in names:
        return True
    any_of = get_type_property(T, 'anyOf')
    if any_of and any([is_nullable(a) for a in any_of]):
        return True
    return False


def get_type_name(type):
    if isinstance(type, str):
        return type
    elif isinstance(type, dict):
        return get_type_name(type.get('type'))
    return None


def get_type_names(type):
    if isinstance(type, dict):
        return get_type_names(type.get('type'))
    if isinstance(type, list):
        return [get_type_name(t) for t in type]
    return None


def is_list(T):
    """Return true if T is a list type or optional list type"""
    base_type = get_type_name(T)
    if base_type:
        # direct type
        return base_type == 'array'

    # optional type, e.g. ["null", "array"] is considered a list
    for check in get_split_types(T):
        if check:
            for item in check:
                if is_list(item):
                    return True


def is_container(T):
    base_type = get_type_name(T)
    if base_type:
        return base_type in {'array', 'object'}
    else:
        for check in get_split_types(T):
            if check and any([is_container(a) for a in base_types]):
                return True
    return False


def is_link(T):
    return bool(get_link(T))


def get_split_types(T):
    return (
        get_type_names(T),
        get_type_property(T, 'anyOf'),
        get_type_property(T, 'oneOf')
    )


def get_link(T):
    base_type = get_type_name(T)
    if base_type:
        if base_type.startswith('@'):
            return base_type[1:]
        if base_type == 'array':
            items = get_type_property(T, 'items')
            return get_link(items) if items else None
        if base_type == 'object':
            additional = get_type_property(T, 'additionalProperties')
            return get_link(additional) if isinstance(additional, dict) else None
        return None

    for check in get_split_types(T):
        if check:
            for item in check:
                link = get_link(item)
                if link:
                    return link

    return None


def validate_object(type, value, throw=False):
    if not isinstance(value, dict) and throw:
        if throw:
            raise TypeValidationError(f'expecting object but got: {value}')
        return False
    return True


def validate_array(type, value, throw=False):
    if not isinstance(value, list) and throw:
        if throw:
            raise TypeValidationError(f'expecting array but got: {value}')
        return False
    return True


def validate_link(type, value, throw=False):
    if not isinstance(value, (object, int, float, str)):
        if throw:
            raise TypeValidationError(f'expecting link but got: {value}')
        return False
    return validate_multi(type, value, throw=throw)


def validate_boolean(type, value, throw=False):
    if not isinstance(value, bool) or (
        isinstance(value, str) and value.lower() not in {'true', 'false'}
    ):
        if throw:
            raise TypeValidationError(f'expecting boolean but got: {value}')
        return False
    return validate_multi(type, value, throw=throw)


def validate_null(type, value, throw=False):
    if value is not None:
        if throw:
            raise TypeValidationError(f'expecting null but got: {value}')
        return False
    return validate_multi(type, value, throw=throw)


def validate_number(type, value, throw=True):
    if not isinstance(value, (int, float, Decimal)):
        # TODO: what about strings with numeric value?
        if throw:
            raise TypeValidationError(f'expecting number but got: {value}')
        return False
    return validate_multi(type, value, throw=throw)


def validate_string(type, value, throw=True):
    if not isinstance(value, str):
        if throw:
            raise TypeValidationError(f'expecting string but got: {value}')
        return False
    return validate_multi(type, value, throw=throw)


def get_type_property(type, key):
    return type.get(key) if isinstance(type, dict) else None


def one(iterable):
    one = False
    for x in iterable:
        if bool(x):
            if one:
                # too many
                return False
            one = True
    return one


def validate_multi(type, value, throw=True):
    any_of = get_type_property(type, 'anyOf')
    all_of = get_type_property(type, 'allOf')
    one_of = get_type_property(type, 'oneOf')
    not_ = get_type_property(type, 'not')
    types = get_type_names(type)


    if types and not any([validate(t, value, throw=False) for t in types]):
        if throw:
            raise TypeValidationError(f'types({types}) not satisfied by: {value}')
        return False
    if any_of and not any([validate(t, value, throw=False) for t in any_of]):
        if throw:
            raise TypeValidationError(f'anyOf({any_of}) not satisfied by: {value}')
        return False
    if all_of and not all([validate(t, value, throw=False) for t in all_of]):
        if throw:
            raise TypeValidationError(f'allOf({any_of}) not satisfied by: {value}')
        return False
    if one_of and not one([validate(t, value, throw=False) for t in one_of]):
        if throw:
            raise TypeValidationError(f'oneOf({any_of}) not satisfied by: {value}')
        return False
    if not_ and validate(not_, value, throw=False):
        if throw:
            raise TypeValidationError(f'not({not_}) was satisfied by: {value}')
        return False
    return True


def validate(type, value, throw=True):
    if value is None:
        # special case for None
        if not is_nullable(type):
            if throw:
                raise TypeValidationError(f'type {type} is not nullable')
            return False
        return True

    base_type = get_type_name(type)

    if base_type == 'array':
        # array
        return validate_array(type, value, throw=throw)
    elif base_type == 'object':
        # object
        return validate_object(type, value, throw=throw)
    elif base_type == 'string':
        # string
        return validate_string(type, value, throw=throw)
    elif base_type == 'null':
        return validate_null(type, value, throw=throw)
    elif base_type == 'number':
        return validate_number(type, value, throw=throw)
    elif base_type == 'boolean':
        return validate_boolean(type, value, throw=throw)
    elif base_type and base_type.startswith('@'):
        # link type
        return validate_link(type, value, throw=throw)
    elif base_type is None or base_type == 'any':
        # any or unspecified type
        return validate_multi(type, value, throw=throw)
