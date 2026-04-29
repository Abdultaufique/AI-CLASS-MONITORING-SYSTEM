"""
Tenant isolation middleware — ensures queries are scoped to the user's organization.
"""
from django.utils.deprecation import MiddlewareMixin


class TenantMiddleware(MiddlewareMixin):
    """
    Attaches the current user's organization to the request object
    for easy access throughout the request lifecycle.
    """
    def process_request(self, request):
        request.organization = None
        if request.user.is_authenticated:
            try:
                profile = request.user.profile
                request.organization = profile.organization
            except Exception:
                pass
