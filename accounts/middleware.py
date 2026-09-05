from django.utils import timezone
from django.shortcuts import redirect
from django.urls import reverse
from .models import UserActivity, UserSession

class BusinessMiddleware:
    """Middleware to set current business in request."""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.user.is_authenticated:
            # Set business in request
            if hasattr(request.user, 'business'):
                request.current_business = request.user.business
            else:
                request.current_business = None
            
            # Update last activity
            UserSession.objects.filter(
                user=request.user,
                session_key=request.session.session_key,
                is_active=True
            ).update(last_activity=timezone.now())
        
        response = self.get_response(request)
        return response

class AuditLogMiddleware:
    """Middleware to log user actions."""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Log view actions for authenticated users
        if request.user.is_authenticated and request.method == 'GET':
            # Skip AJAX and API requests
            if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                if not request.path.startswith('/api/'):
                    # Skip static and media files
                    skip_paths = ['/static/', '/media/', '/favicon.ico']
                    if not any(request.path.startswith(path) for path in skip_paths):
                        try:
                            UserActivity.objects.create(
                                user=request.user,
                                action='VIEW',
                                model_name='Page',
                                object_id=request.path,
                                ip_address=request.META.get('REMOTE_ADDR'),
                                user_agent=request.META.get('HTTP_USER_AGENT', '')
                            )
                        except:
                            pass
        
        return response