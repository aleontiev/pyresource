from typing import Union, Mapping, List

Type = Union[
    str,
    Mapping[str, 'Type'],
    List['Type']
]

def validate(T):
    return True

CONTAINERS = {
    '{',
    '[',
    '?'
}


def is_list(T):
    if T and isinstance(T, str):
        return T.startswith('[') or T.startswith('?[')
    elif isinstance(T, list):
        return all([is_list(t) for t in T])
    elif isinstance(T, dict):
        return all([is_list(t) for t in T.values()])
    return False


def is_link(T):
    if T and isinstance(T, str):
        return '@' in T
    elif isinstance(T, list):
        return all([is_link(t) for t in T])
    elif isinstance(T, dict):
        return all([is_link(t) for t in T.values()])
    return False


def get_link(T):
    link = is_link(T)
    if link:
        return True, ''.join(T[T.index('@') + 1:])
    else:
        return None, None


def get_container(T):
    if T and isinstance(T, str):
        if T[0] in CONTAINERS:
            return T[0], T[1:]
        else:
            return None, None
    else:
        return None, None
