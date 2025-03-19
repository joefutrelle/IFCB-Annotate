from django.urls import path, re_path

from . import views

urlpatterns = [
    path('', views.HomePageView.as_view()),
    re_path(r'classify/?', views.ClassifyPageView.as_view()),
    re_path(r'submitupdates/?', views.SubmitUpdatesPageView.as_view()),
    re_path(r'login/?', views.LoginPageView.as_view()),
    re_path(r'register/?', views.RegisterPageView.as_view()),
    re_path(r'logout/?', views.LogoutPageView.as_view()),
    re_path(r'getzip/?', views.ZipDownloadPageView.as_view()),
    re_path(r'cachebins/?', views.CacheBinPageView.as_view()),
    re_path(r'validatebins/?', views.ValidateBinsView.as_view()),
    re_path(r'searchbins/?', views.SearchBinsView.as_view()),
]