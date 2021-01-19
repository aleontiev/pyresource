from .utils import cached_property
from .resource import Resource
from .version import version


class Server(Resource):
    class Schema:
        id = "server"
        source = None
        name = "server"
        singleton = True
        space = "."
        description = "server description"
        fields = {
            "version": {
                "type": "string",
                "default": version
            },
            "url": {
                "type": "string",
                "primary": True
            },
            "spaces": {
                "type": {
                    "type": "array",
                    "items": "@spaces"
                },
                "inverse": "server",
                "default": [],
            },
            "features": {
                "type": {
                    "anyOf": [
                        {
                            "type": "object"
                        },
                        {
                            "type": "array",
                            "additionalProperties": {
                                "type": "string"
                            }
                        }
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
                        "operators": [
                            "max", "min", "sum", "count", "average", "distinct"
                        ]
                    },
                    "sort": True,
                    "inspect": True,
                    "action": True,
                },
            },
            "types": {
                "type": {
                    "type": "array",
                    "items": "@types"
                },
                "default": [],
                "inverse": "server",
            },
        }
    """

Links

A link is a special field type representing a relationship between resources.
Links provide resources with the ability to pull in related data on demand.

For example, lets say we have "posts" and "comments" resources,
with field posts.comments {"type": {"is": "array", "of": "@comments"}, "inverse": "post"}
...and inverse field comments.post {"type": "@posts", "inverse": "comments"}

A comment's post is represented by a link.

Links can have one of several types of representation:

1) Excluded

Like any other field, a link may be excluded, in which case it does not render at all
For example, we can request comments with just the ID and body fields, without the post field.

Request:
GET /api/v1/comments/?with=id,body

Response:
{
    "key": {"comments": ["1", "2", "3"]},
    "data": {
        "comments": {
            "1": {"id": 1, "body": "...1"},
            "2": {"id": 2, "body": "...2"},
            "3": {"id": 3, "body": "...3"}
        },
    }
}

2) String ID (no URLs)

By default, a link is rendered as a resource-local string ID, which must not contain /

Request:
GET /api/v1/comments/1/

Response:
{
    "key": {"comments": "1"},
    "data": {
        "comments": {
            "1": {"id": "1", "body": "this is a great post!", "post": "123", "created": "2019-01-01"}
        }
    }
}

Request:
GET /api/v1/comments/1/post/

{
    "key": {
        "posts": "123"
    },
    "data": {
        "posts": {"123": {"id": "123", "body": "hey Im a post"}}
    }
}

Request
GET /api/v1/posts/1/comments/?with.user=id,name
{
    "key": {
        "comments": ["1", "2"]
    },
    "data": {
        "comments": {
            "1": {"id": "1", "body": "hi there", "user": "1"},
            "2": {"id": "2", "body": "hi again", "user": "2"}
        },
        "users": {
            "1": {"id": "1", "name": "Joe"},
            "2": {"id": "2", "name": "John"}
        }
    }
}
3) URL ID

A link may be rendered as an URL ID, either absolute (with scheme and host) or relative to the host
This is useful for generic relationships.

Request:
GET /api/v1/tags/?where:name:in=level
                 &where:name:in=emotional
                 &with=tag
                 &sort=tag
                 &with.items=body
                 &group:item_count:count=items.id
                 &with.subtags=tag
                 &where.subtags:tag:like:1=test
                 &where.subtags:tag:equals$:2=parent.tag
                 &where.subtags=1,~2
                 &with.subtags.subtags=tag
                 &with.creator=*,-email

Query:
{
    "action": "get",
    "space": "v1",
    "resource": "tags",
    "record": null,
    "field": null,
    "query": {
        "group": {
            "most_recent_tag": {
                "max": "created"
            },
            "item_count": {
                "count": "items.id"
            }
        },
        "where": {
             "in": [
                'name',
                ["'level'", "'emotional'"]
            }
        },
        "sort": ["tag"],
        "fields": {
            "tag": True,
            "subtags": {
                "where": {
                    "or": [{
                        "like": ['tag', '"test"']
                    }, {
                        "not": {
                            "=": [
                                "tag", "parent.tag"
                            ]
                        }
                    }]
                },
                "fields": {
                    "tag": True,
                    "subtags": {
                        "tag": True
                    }
                }
            },
            "items": {
                "fields": {
                    "body": True
                }
            },
            "creator": {
                "fields": {
                    "*": True,
                    "email": False
                }
            }
        }
    },
}

SQL:

(level 1: tags) SELECT tag, creator_id, id, max('created'.) as most_recent_tag OVER () FROM tags WHERE tag in ["level", "emotional"] AND id > LAST_ID_TAGS ORDER BY id LIMIT 1001
    ... 500 (no pagination)
(level 2: subtags) SELECT tag, subtag FROM tags WHERE parent_id IN (SELECT id FROM tags ORDER BY id) AND id > LAST_ID_TAGS_SUBTAGS ORDER BY id LIMIT 1001
    ... 1001 (paginate)
(level 2: creator) SELECT created, updated, name FROM tags WHERE parent_id IN (SELECT id FROM tags ORDER BY id) > LAST_ID_TAGS_CREATOR ORDER BY id LIMIT 1001
    ... 1
(level 3: subtags.subtags) SELECT tag FROM tags WHERE parent_id IN (SELECT ID FROM tags WHERE parent_id IN (SELECT id FROM tags ORDER BY id) ORDER BY id) LIMIT 1001
    ... 50
(level 2: items) SELECT body, id FROM (SELECT body, id FROM TableA UNION ALL SELECT body, id FROM TableB ...) WHERE tag_id IN (SELECT id FROM tags ORDER BY id) LIMIT 1001
    ... 1001 (paginate)



Response:
{
    "key": {
        tags": ["1", "2", "10", "11"]
    },
    "data": {
        "tags": {
            "1": {"tag": "happy", "creator": "1"},
            "2": {"tag": "sad", "creator": null},
            "3": {"tag": "emotional", "creator": "1"},
            "11": {"tag": "depressed", "creator": null}
            "21": {"tag": "excited", "creator": "2"}
        },
        "posts": {
            "123": {"body": "this is great!"},
            "124": {"body": "this is not great"},
        },
        "comments": {
            "600": {"body": "this rules"},
            "600": {"body": "this sucks"},
        },
        "users": {
            "1": {"name": "Jo"}
            "2": {}
        },
        "tags.subtags": {
            "1": ["21"],
            "2": ["11"],
            "3": ["1", "2"]
        },
        "tags.items": {
            "1": [
                "posts/123",
                "comments/601"
            ],
            "2": [
                "posts/124",
                "comments/600"
            ]
        }
    }
}
    """
    def __init__(self, *args, **kwargs):
        super(Server, self).__init__(*args, **kwargs)
        self._setup = False

    @cached_property
    def spaces_by_name(self):
        result = {}
        for space in self.spaces:
            result[space.name] = space
        return result

    @cached_property
    def root(self):
        from .space import Space

        return Space(
            space=".",
            name=".",
            server=self,
            resources=[
                "spaces",
                "resources",
                "types",
                "fields",
                "server"
            ],
        )

    def get_resource_by_id(self, id):
        return self.root.resolve_record('resources', id)

    def setup(self):
        if not self._setup:
            self.add("spaces", self.root)
            self.add("types", [
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
                "array",
            ])
        self._setup = True

    @cached_property
    def urls(self):
        return self.get_urls()

    def get_urls(self):
        patterns = []
        self.setup()
        for space in self.spaces:
            patterns.extend(space.urls)
        return patterns
