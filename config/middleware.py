from django.utils.cache import patch_cache_control, patch_vary_headers


class PrivateAPIResponseMiddleware:
    """CV, conversation and account responses must not enter HTTP caches."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/api/') and not request.path.startswith('/api/templates/'):
            patch_cache_control(response, private=True, no_store=True)
            patch_vary_headers(response, ['Authorization'])
        return response
