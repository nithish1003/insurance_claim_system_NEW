from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

class AjaxAuthenticationMiddleware:
    """
    Middleware to ensure that AJAX requests from the frontend receive a 
    proper JSON error response instead of a 302 redirect to the login page 
    when the session has expired or the user is unauthenticated.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or self._is_json_request(request)

        # 1. Handle session expiry redirects
        if response.status_code == 302 and is_ajax:
            login_url = reverse('accounts:login')
            if login_url in response.url.lower() or 'login' in response.url.lower():
                return JsonResponse({
                    'error': 'Session expired. Please log in again.',
                    'code': 'AUTHENTICATION_REQUIRED',
                    'login_url': f"{login_url}?next={request.path}"
                }, status=401)
        
        # 2. Handle other error codes for AJAX
        if is_ajax and response.status_code in [403, 404, 500]:
            # If it's already JSON, let it through
            if 'application/json' in response.get('Content-Type', ''):
                return response
                
            error_messages = {
                403: 'Permission denied.',
                404: 'Resource not found.',
                500: 'Internal server error. Please try again later.'
            }
            
            return JsonResponse({
                'error': error_messages.get(response.status_code, 'An error occurred.'),
                'status_code': response.status_code
            }, status=response.status_code)
            
        return response

    def _is_json_request(self, request):
        return (
            request.content_type == 'application/json' or
            request.META.get('HTTP_ACCEPT') == 'application/json' or
            request.path.startswith('/api/') # Common pattern
        )
