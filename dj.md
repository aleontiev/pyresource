### Using DJ

#### Installation

You can add this to your project with [DJ](https://djay.io), a developer utility tool for Django that wraps pyenv, virtualenv, pip, and poetry.
It allows you to quickly add `django-resource` to your project and set up your own resources with the CLI:

``` bash 
    dj add django-resource
```

The above command will run an initialization blueprint to automatically add the code to:
- Add `django_resource` to `settings.py:INSTALLED_APPS`
- Add a `DJANGO_RESOURCE` settings object to `settings.py` with sane defaults
- Create a `resources` package within your main package
- Add a URL mount under `/resources` referencing the server

New blueprints will become available to generate spaces and resources.

#### Adding spaces

Generate a space, passing in a name:

``` bash
    dj generate django_resource.space --name=v0
```

#### Adding resources

Generate a resource, passing in a space, name, and model

``` bash
    dj generate django_resource.resource --space=v0 --name=users --model=auth.User
```

#### Running the server

``` bash
    dj serve 9000
```

Visit "http://localhost:9000/resources"
