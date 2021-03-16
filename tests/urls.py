from pyresource.django.urls import get_urlpatterns
from .server import get_server

server = get_server()
urlpatterns = get_urlpatterns(server)
