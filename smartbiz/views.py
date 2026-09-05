from django.shortcuts import redirect, render
from django.http import JsonResponse


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "home.html")


def onboarding(request):
    """Safe landing page for authenticated users who skipped business setup."""
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    return render(request, "onboarding.html")


def custom_404(request, exception):
    """Custom 404 error page."""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'Resource not found'}, status=404)
    return render(request, 'errors/404.html', status=404)

def custom_500(request):
    """Custom 500 error page."""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'Internal server error'}, status=500)
    return render(request, 'errors/500.html', status=500)

def custom_403(request, exception):
    """Custom 403 error page."""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'Permission denied'}, status=403)
    return render(request, 'errors/403.html', status=403)