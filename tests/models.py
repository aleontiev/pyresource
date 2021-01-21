from datetime import datetime
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser
from django.db.models.fields import NOT_PROVIDED
from django.contrib.postgres import fields as postgres


class MakeMixin:
    @classmethod
    def generate(cls, field, counter=None):
        # if auto-now, use now
        if getattr(field, 'auto_now_add', False) or getattr(field, 'auto_now', False):
            return datetime.utcnow()
        # if has choices, return first choice
        if field.choices:
            return field.choices[0][0]
        # use field type, try to generate unique values
        if isinstance(field, models.DateTimeField):
            return datetime.utcnow()
        if isinstance(field, models.DateField):
            return datetime.utcnow().date()
        if isinstance(field, models.TimeField):
            return datetime.utcnow().now()
        if isinstance(field, (models.TextField, models.CharField)):
            suffix = ''
            if field.name == 'email':
                suffix = '@test.com'
            return f'{field.name}-{counter}{suffix}'
        if isinstance(field, models.BooleanField):
            return True
        if isinstance(
            field, (
                models.PositiveIntegerField,
                models.FloatField,
                models.DecimalField
            )
        ):
            return int(datetime.utcnow().strftime('%s'))
        if isinstance(field, (postgres.JSONField, postgres.ArrayField)):
            # guess that if its an array field, child is either int/str
            # and might have min length
            return [datetime.utcnow().strftime('%s')]
        if isinstance(field, models.UUIDField):
            return uuid.uuid4()
        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            related = field.related
            if hasattr(related, 'make'):
                return related.make()
            else:
                # use cls.make to build any other model
                return cls.make_(related)
        else:
            raise ValueError(
                f'Cannot generate field {field.name} on model {field.model._meta.model_name}'
            )

    @classmethod
    def make_other(cls, other):
        return

    @classmethod
    def make(cls, **defaults):
        other = defaults.pop('_other', None)
        if other:
            cls = other

        record = {}
        counter = getattr(cls, '_make_counter', 1)

        for field in cls._meta.get_fields():
            if field.name in defaults:
                # do not generate, use provided value
                value = defaults[field.name]
            else:
                if (
                    field.null or
                    isinstance(field, (models.ManyToManyField, models.AutoField))
                    or field.default is not NOT_PROVIDED
                ):
                    # skip nullable fields, many-to-many fields, auto fields, default fields
                    continue
                # generate
                value = cls.generate(field, counter=counter)
            record[field.name] = value

        record = cls.objects.create(**record)
        counter += 1
        cls._make_counter = counter
        return record


class Location(MakeMixin, models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.TextField()
    address = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)


class Group(MakeMixin, models.Model):
    id = models.UUIDField(primary_key=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    name = models.TextField()
    is_active = models.BooleanField(default=True)


class Membership(MakeMixin, models.Model):
    user = models.ForeignKey('User', related_name='memberships', on_delete=models.CASCADE)
    group = models.ForeignKey('Group', related_name='membership', on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    status = models.TextField()


class User(MakeMixin, AbstractBaseUser):
    USERNAME_FIELD = 'email'

    id = models.UUIDField(primary_key=True)
    first_name = models.TextField(null=True)
    last_name = models.TextField(null=True)
    email = models.TextField(unique=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)
    location = models.ForeignKey(
        Location,
        related_name='users',
        null=True,
        on_delete=models.SET_NULL
    )
    groups = models.ManyToManyField(
        Group,
        through='Membership',
        related_name='users'
    )
    roles = models.TextField(
        null=True,
        help_text="Comma-separated role names"
    )
