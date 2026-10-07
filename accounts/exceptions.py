from rest_framework.views import exception_handler as drf_exception_handler

def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        codes = {
            400: 'validation_error',
            401: 'authentication_failed',
            403: 'permission_denied',
            404: 'not_found',
            405: 'method_not_allowed',
            409: 'version_conflict',
            429: 'throttled',
        }
        response.data = {'error':{'code':codes.get(response.status_code,'request_error'),
                                  'details':response.data}}
    return response
