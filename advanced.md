# Advanced Topics

## Query translation

Most of the work in Resource and other data-mapper libraries like GraphQL goes into translating an API-level query tree into a series of SQL queries, one for each node in the tree.

### Root query

The simplest query has just one node: the root node. Every other tree has a root node as well as additional descendant nodes.

For example, lets suppose we have resources "users" and "groups" sourced by tables "users" and "groups" (as defined in `django.auth.models`). We can assume these two fields are connected by a link table called "user_groups".

Consider then the following query:

```
    /api/version/users?take=id,name&sort=name&page:size=50&where:is_active=true
```

This query has just one node and is fetched using a simple SELECT:

``` SQL
    SELECT users.id, users.name
    FROM users
    WHERE is_active = true
    ORDER BY name
    LIMIT 51
```

### Prefetch queries

If we want to extend this query to also include the users' group names:

```
    /api/version/users?take=id,name&sort=name&page:size=50&where:is_active=true&take.groups=id,name
```

...this would require additional SQL queries or aggregation, since there can be more than one group for each user.

In Resource, we choose to avoid the aggregation approach because it is harder to generalize across RDBMS systems and use-cases, but it might look something like this in Postgres 9+:

``` SQL
    SELECT users.id, users.name, json_agg(groups.name)
    FROM users
    LEFT JOIN user_groups ON user_groups.user_id = users.id
    INNER JOIN groups ON groups.id = user_groups.group_id
    WHERE is_active = true
    GROUP BY users.id, users.name
    ORDER BY name
    LIMIT 51
```

Note that the addition of joins, grouping, and aggregate function make this query much more complicated.

Instead, we opt to use one additional "prefetch query" to fetch these groups in a followup to the users query. This can sometimes be slower than the aggregation approach, but it is easier to maintain, works across all RDBMS systems, scales better to large query trees, and supports prefetching across resources that are in different databases.

In order to do this, we first need collect the row IDs from the root query. Let's assume that the root query returns the IDs `1, 2, 3`. Knowing this, we can find the groups that are connected to these user IDs:

``` SQL
    SELECT groups.id, user_groups.user_id, groups.name
    FROM user_groups
    INNER JOIN groups ON user_groups.group_id = groups.id
    WHERE user_id IN (1, 2, 3)
```

Note that we also return the user IDs so that the results of this prefetch query and the root query can be merged together using the user ID as the merge key.

### Prefetch with limits

One complication to the above approach is that we may want to prefetch and also limit related data. For example, what if we modify the above query so that only the newest 3 groups are returned for each user?

```
    /api/version/users
        ?take=id,name
        &sort=name
        &page:size=50
        &where:is_active=true
        &take.groups=id,name
        &sort.groups=-created
        &page.groups:size=3
```

This is difficult to express in SQL using the prefetch approach; we can't add a `LIMIT` onto the prefetch query, because that would limit the total number of groups instead of the number of groups per user:

``` sql
    SELECT groups.id, user_groups.user_id, groups.name
    FROM user_groups
    INNER JOIN groups ON user_groups.group_id = groups.id
    WHERE user_id IN (1, 2, 3)
    ORDER BY groups.created
    LIMIT 3 -- wrong, we don't just want 3 results
```

Of course, we can make one query for each user with this limit, but that would not scale well for larger numbers of users (the "N+1" query problem).

Instead, we can use a combination of subqueries or CTEs and window functions:
- The window function `row_number()` is applied over partitions by user ID sorted by the group created timestamp, satisfying our need to order related groups for each user
- The subquery allows us to filter on the window function by temporarily storing the window results (not normally allowed because it is a virtual field computed in a post-filtering step)


``` sql
WITH T as (
    SELECT
        groups.id as id,
        user_groups.user_id as user_id,
        groups.name as name,
        row_number() over (partition by user_groups.user_id order by groups.created) as row,
    FROM user_groups
    INNER JOIN groups ON user_groups.group_id = groups.id
    WHERE user_id IN (1, 2, 3)
)
SELECT *
FROM T
WHERE T.row <= 3
```

To make queries like this, we can use the `django-cte` package (which will hopefully be added directly to Django 4+ as it supports these more advanced use-cases!)

Using `django-cte` looks like this:

```
from django_cte import With, CTEManager

def get_manager(self, model):
    if not hasattr(model, 'cte_objects'):
        manager = CTEManager()
        manager.contribute_to_class(model, 'cte_objects')
    return model.cte_objects

With.get_manager = get_manager

cte = With(
    Group.objects.filter(users__in=[1, 2, 3]).annotate(
        row_number=Window(
            expression=RowNumber(),
            partition_by=['users'],
            order_by=['created']
        )
    )
)
queryset = cte.queryset().with_cte(cte).filter(
    row_number__lte=3
)
```





