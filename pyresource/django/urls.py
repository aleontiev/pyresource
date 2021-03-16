from urllib.parse import urlparse
from django.urls import re_path
from django.http import JsonResponse


methods_to_actions = {
    'GET': 'get',
    'PUT': 'set',
    'POST': 'add',
    'PATCH': 'edit',
    'DELETE': 'delete',
    'OPTIONS': 'explain'
}


def make_dispatch(server, base):
    def dispatch(request, **kwargs):
        """Dispatch a Django/WSGI request to a pyresource.Server"""
        querystring = request.GET.urlencode()
        method = request.method
        path = request.path
        # normalize starting slash
        if path[0] == '/':
            path = path[1:]

        if not path.startswith(base):
            raise Exception(
                f'unexpected request path {path} when base path is {base}'
            )
        # remove base path
        path = path.replace(base, '', 1)
        query = f'{path}?{querystring}' if querystring else path
        query = server.query(query)
        if 'action' not in request.GET:
            # determine action from request method
            # otherwise, use action passed in to request
            action = methods_to_actions.get(method)
            if not action:
                raise Exception(
                    f'unsupported method {method}'
                )
            query = query.action(action)
        response = query.execute(response=JsonResponse, request=request)
        return response
    return dispatch


dispatches = {}
def get_dispatch_for(server, base):
    """Get dispatch method for a server"""
    url = server.url
    global dispatches
    if url not in dispatches:
        dispatches[url] = make_dispatch(server, base)
    return dispatches[url]


def get_urlpatterns(server):
    """Get Django-compatible urlpatterns from a server"""
    base = urlparse(server.url).path
    if base[0] == '/':
        base = base[1:]
    dispatch = get_dispatch_for(server, base)
    regex = rf'^{base}.*$'
    return [re_path(regex, dispatch)]
