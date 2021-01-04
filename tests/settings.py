SECRET_KEY = 'test'
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
    }
]
DATABASES = {}
DATABASES["default"] = {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": "resource_dev",
    "TEST": {"NAME": "resource_test"},
}
INSTALLED_APPS = (
    "django.contrib.sessions",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "tests"
)
AUTH_USER_MODEL = "tests.User"
