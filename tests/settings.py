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
    'django.contrib.sites',
    "tests"
)
AUTH_USER_MODEL = "tests.User"
ROOT_URLCONF = "tests.urls"

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware'
]
