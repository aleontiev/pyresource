from django.db import models
from django.contrib.auth.models import AbstractBaseUser


class Location(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.TextField()
    address = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)


class Group(models.Model):
    id = models.UUIDField(primary_key=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    name = models.TextField()


class Membership(models.Model):
    user = models.ForeignKey('User', related_name='memberships', on_delete=models.CASCADE)
    group = models.ForeignKey('Group', related_name='membership', on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    status = models.TextField()


class User(AbstractBaseUser):
    USERNAME_FIELD = 'email'

    id = models.UUIDField(primary_key=True)
    first_name = models.TextField(null=True)
    last_name = models.TextField(null=True)
    email = models.TextField(unique=True, null=True)
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
        null=True,
    )
    roles = models.TextField(
        null=True,
        help_text="Comma-separated role names"
    )
