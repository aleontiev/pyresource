import re

PAGE = 'page'
INSPECT = 'inspect'
ACTION = 'method'
TAKE = 'take'
SORT = 'sort'
GROUP = 'group'
WHERE = 'where'
FIELD = 'field'
RECORD = 'record'
DATA = 'data'
SPACE = 'space'
RESOURCE = 'resource'


LEVELED_FEATURES = {
    GROUP,
    TAKE,
    SORT,
    WHERE,
    PAGE,
}
ROOT_FEATURES = {
    INSPECT,
    ACTION,
    FIELD,
    RECORD,
    DATA,
    SPACE,
    RESOURCE
}
FEATURES = LEVELED_FEATURES | ROOT_FEATURES

FEATURE_REGEX = re.compile('^[-A-Za-z0-9_]+')
FIELD_SEPARATOR_REGEX = re.compile('[^*A-Za-z0-9_-]')


def get_feature(key):
    """Get feature given a query key

    Returns:
        feature or None if not a supported feature
    """
    feature = FEATURE_REGEX.match(key)
    if feature:
        feature = feature.group(0).lower()
    else:
        feature = None

    return feature


def get_feature_separator(feature):
    if feature in LEVELED_FEATURES:
        return ':'
    else:
        return '.'


def get_sort_fields(value):
    if isinstance(value, list):
        value = ','.join(value)

    return FIELD_SEPARATOR_REGEX.split(value)


def get_take_fields(value):
    if isinstance(value, list):
        value = ','.join(value)

    fields = FIELD_SEPARATOR_REGEX.split(value)
    result = {}
    for field in fields:
        show = True
        if field.startswith('-'):
            field = field[1:]
            show = False
        result[field] = show
    return result


class NestedFeature(object):
    """Helper class for Query"""
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
        args = [self.level] + list(args)
        # call back to query with arguments
        return getattr(self.query, "_{}".format(self.name))(*args, **kwargs)
