from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import StaffLivreurCreateView
from . import views

urlpatterns = [
    # tes routes ici
    
    path('', views.index, name='home'),
    path('boutique/', views.boutique, name='boutique'),
    path('a-propos/', views.about, name='about'),

    # Auth
    path('accounts/login/', views.custom_login, name='login'),
    path('accounts/logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('accounts/register/', views.register, name='register'),

    # Redirections rôle
    path('dashboard/', views.dashboard, name='dashboard'),
    path('post-login/', views.post_login_redirect, name='post_login_redirect'),
    path('ajouter-personnel/', StaffLivreurCreateView.as_view(), name='ajout'),
]
