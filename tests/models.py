from django.db import models
from django.contrib.auth.models import AbstractBaseUser

class Location(models.Model):
    name = models.TextField()
    address = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)


class User(AbstractBaseUser):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    location = models.ForeignKey(Location, null=True, on_delete=models.SET_NULL)
