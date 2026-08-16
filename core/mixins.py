from django.contrib.auth.mixins import LoginRequiredMixin as DjangoLoginRequiredMixin
from django.http import JsonResponse
from django.views import View


class LoginRequiredMixin(DjangoLoginRequiredMixin):
    """Enforce login with Arabic-friendly redirect."""
    pass


class AjaxRequiredMixin:
    """Restrict view to AJAX requests only."""
    def dispatch(self, request, *args, **kwargs):
        if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'AJAX only'}, status=400)
        return super().dispatch(request, *args, **kwargs)


class StaffRequiredMixin(LoginRequiredMixin):
    """Restrict view to staff users."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            from django.contrib import messages
            from django.shortcuts import redirect
            messages.error(request, 'ليس لديك صلاحية الوصول إلى هذه الصفحة.')
            return redirect('production:dashboard')
        return super().dispatch(request, *args, **kwargs)
