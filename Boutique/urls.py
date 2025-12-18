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
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/categories/', views.admin_categories, name='admin_categories'),
    path('admin-panel/categories/nouvelle/', views.admin_category_create, name='admin_category_create'),
    path('admin-panel/categories/<int:pk>/modifier/', views.admin_category_update, name='admin_category_update'),
    path('admin-panel/categories/<int:pk>/supprimer/', views.admin_category_delete, name='admin_category_delete'),
    path('admin-panel/produits/', views.admin_products, name='admin_products'),
    path('admin-panel/produits/nouveau/', views.admin_product_create, name='admin_product_create'),
    path('admin-panel/produits/<int:pk>/modifier/', views.admin_product_update, name='admin_product_update'),
    path('admin-panel/produits/<int:pk>/supprimer/', views.admin_product_delete, name='admin_product_delete'),
    path('admin-panel/commandes/', views.admin_commande, name='admin_commande'),
]
