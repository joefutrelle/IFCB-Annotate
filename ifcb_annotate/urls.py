"""
URL configuration for ifcb_annotate project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.views import serve
from django.urls import path, re_path, include

urlpatterns = [
    path('', include('web.urls')),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    # Behind a proxy that strips FORCE_SCRIPT_NAME, static requests arrive as
    # /static/... instead of STATIC_URL, so the dev server's own static handler
    # misses them. Listed first because web.urls' unanchored patterns would
    # otherwise match paths like static/javascript/login.js.
    urlpatterns.insert(0, re_path(r'^static/(?P<path>.*)$', serve))
