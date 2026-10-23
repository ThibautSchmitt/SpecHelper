from django.urls import path

from core.api import api
from core.web_security import login_view, logout_view, session_view

urlpatterns = [
    path("api/access/session", session_view),
    path("api/access/login", login_view),
    path("api/access/logout", logout_view),
    path("api/", api.urls),
]
