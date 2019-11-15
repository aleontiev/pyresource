from typing import Union, Mapping, List

Type = Union[
    str,
    Mapping[str, 'Type'],
    List['Type']
]

def validate(type):
    return True
