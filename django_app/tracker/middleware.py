from django.contrib.auth import get_user_model, login


class AutoLoginMiddleware:
    """Signs every visitor in as the studio owner, for a trusted home network."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            User = get_user_model()
            user = User.objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
            if user is None:
                user = User.objects.create_superuser("studio", password=None)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)


def login_settings(request):
    from django.conf import settings

    return {"require_login": settings.REQUIRE_LOGIN}
