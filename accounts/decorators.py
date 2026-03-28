from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from functools import wraps
from django.contrib import messages

def role_required(allowed_roles=[]):
    """
    Decorator for views that checks if the logged-in user has a specific role.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('accounts:login')
            
            # Admins always have access to everything
            if request.user.is_superuser or request.user.role == 'admin':
                return view_func(request, *args, **kwargs)
            
            if request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            
            messages.error(request, "🛡️ Access Denied: You do not have permission to view this department.")
            return redirect('accounts:unauthorized')
        return _wrapped_view
    return decorator

def admin_only(view_func):
    """Only superusers or admin role allowed."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.is_superuser or request.user.role == 'admin':
            return view_func(request, *args, **kwargs)
        
        messages.error(request, "🚫 Security Violation: Administrative credentials required.")
        return redirect('accounts:unauthorized')
    return _wrapped_view

def staff_or_admin(view_func):
    """Staff and Admins allowed."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.is_superuser or request.user.role in ['admin', 'staff']:
            return view_func(request, *args, **kwargs)
        
        messages.error(request, "⚠️ Restricted Area: Claims Processing Staff only.")
        return redirect('accounts:unauthorized')
    return _wrapped_view

def staff_only(view_func):
    """
    Exclusive access for staff members. 
    Admins are permitted for quality assurance.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.is_superuser or request.user.role in ['admin', 'staff']:
            return view_func(request, *args, **kwargs)
            
        messages.error(request, "⚠️ Restricted Area: Claims Processing Staff credentials required.")
        return redirect('accounts:unauthorized')
    return _wrapped_view

