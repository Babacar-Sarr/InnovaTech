from django.shortcuts import render, redirect, get_object_or_404
from itertools import count
from os import truncate
from PIL import Image, ImageDraw, ImageFont
from functools import wraps
import json
import os
from django.conf import settings

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import logout, update_session_auth_hash, login, authenticate
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.auth.models import User
from django.contrib.admin.views.decorators import staff_member_required as staff_required
from django.urls import reverse_lazy, reverse
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.db.models import Q, Sum, Count
from django.db.models.functions import TruncDate
from django.db import transaction
from .utils import envoyer_mail_statut_commande 
from Boutique.forms import (
    AdminProfileForm, AdresseForm, CategorieForm, DelivererCreateForm, 
    DelivererProfileForm, DelivererProfileUpdateForm, DelivererUserUpdateForm, 
    ProduitForm, UserUpdateForm,RegisterStep1Form, RegisterStep2Form, RegisterStep3Form
)
from .models import (
    Produit, Categorie, Commande, CommandeItem, PanierItem, UserProfile, 
    Note, Adresse, RoleChoices
)
from .constants import FRAIS_LIVRAISON_DEFAUT
# Create your views here.

# ===================================================================
# FONCTIONS UTILITAIRES
# ===================================================================

def _unit_price(prod):
    """Récupère le prix unitaire d'un produit (promo ou normal)"""
    return getattr(prod, 'prix_promo', None) or getattr(prod, 'prix', 0) or 0

def _pending_choice_for_statut():
    """Récupère le choix 'en attente' pour le statut de commande"""
    try:
        field = Commande._meta.get_field('statut')
        choices = getattr(field, 'choices', []) or []
        mapping = {str(code).upper(): code for code, _ in choices}
        for key in ('EN_ATTENTE', 'EN ATTENTE', 'PENDING'):
            if key in mapping:
                return mapping[key]
    except Exception:
        pass
    return 'EN_ATTENTE'

def _get_cart_count(request):
    """Récupère le nombre d'articles dans le panier"""
    if request.user.is_authenticated:
        return PanierItem.objects.filter(user=request.user).aggregate(total=Sum('quantite'))['total'] or 0
    cart = request.session.get('panier', {})
    return sum(int(v.get('quantite', 0)) for v in cart.values())

def is_livreur(user):
    """Vérifie si l'utilisateur est un livreur"""
    return getattr(getattr(user, 'userprofile', None), 'role', None) == RoleChoices.LIVREUR

# Fonctions pour les livreurs
def _livreur_orders_queryset(user=None):
    """Récupère les commandes pour un livreur"""
    return Commande.objects.select_related('user').order_by('-id')

def _livreur_stats(orders):
    """Calcule les statistiques pour un livreur"""
    from django.db.models import Sum, Count
    from django.utils import timezone
    
    today = timezone.now().date()
    
    # Utiliser la constante partagée
    FRAIS_LIVRAISON = FRAIS_LIVRAISON_DEFAUT
    
    # Compter les commandes par statut
    pending = orders.filter(statut='EN_ATTENTE').count()
    in_progress = orders.filter(statut='EN_COURS').count()
    completed = orders.filter(statut='LIVREE').count()
    
    # Commandes livrées aujourd'hui
    delivered_today = orders.filter(
        statut='LIVREE',
        date_commande__date=today
    ).count()
    
    # Revenus basés sur les frais de livraison
    # Seules les commandes livrées génèrent des revenus pour le livreur
    completed_orders = orders.filter(statut='LIVREE')
    
    # Revenus totaux = nombre de commandes livrées × frais de livraison
    revenue_total = completed_orders.count() * FRAIS_LIVRAISON
    
    # Revenus du jour = commandes livrées aujourd'hui × frais de livraison
    revenue_today = delivered_today * FRAIS_LIVRAISON
    
    # Revenus du mois
    revenue_this_month = orders.filter(
        statut='LIVREE',
        date_commande__month=today.month,
        date_commande__year=today.year
    ).count() * FRAIS_LIVRAISON
    
    return {
        'count_all': orders.count(),
        'pending': pending,
        'in_progress': in_progress,
        'completed': completed,
        'delivered_today': delivered_today,
        'revenue_total': revenue_total,
        'revenue_today': revenue_today,
        'revenue_this_month': revenue_this_month,
        'frais_livraison': FRAIS_LIVRAISON,
    }

# ===================================================================
# DÉCORATEURS PERSONNALISÉS
# ===================================================================

def admin_required(view_func):
    """Décorateur pour les vues admin uniquement"""
    @login_required
    @user_passes_test(lambda u: u.is_staff, login_url='/login/')
    def wrapper(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return wrapper

def client_only(view_func):
    """Décorateur pour les vues clients uniquement (pas d'admin)"""
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff:
            return redirect('admin_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper

# ===================================================================
# VUES POUR la BOUTIQUE(CLIENT)
# ===================================================================
            # ===================================================================
            # VUES PUBLIQUES (sans authentification)
            # ===================================================================
def index(request):
    """Page d'accueil - redirige vers la boutique"""
    return redirect('boutique')

def accueil(request):
    """Ancienne page d'accueil - redirige vers la boutique"""
    return redirect('boutique')

def boutique(request):
    """Vue boutique - liste des produits accessible à tous"""
    produits_qs = Produit.objects.all()

    # Recherche
    search = request.GET.get('search')
    if search:
        produits_qs = produits_qs.filter(Q(nom__icontains=search) | Q(description__icontains=search))

    # Filtrage par catégorie
    categorie_id = request.GET.get('categorie')
    try:
        categorie_selected_int = int(categorie_id) if categorie_id else None
    except (TypeError, ValueError):
        categorie_selected_int = None

    if categorie_selected_int:
        produits_qs = produits_qs.filter(Q(categories__id=categorie_selected_int)).distinct()

    # Tri
    sort = request.GET.get('sort', 'nom')
    if sort == 'prix_asc':
        produits_qs = produits_qs.order_by('prix')
    elif sort == 'prix_desc':
        produits_qs = produits_qs.order_by('-prix')
    elif sort == 'date':
        produits_qs = produits_qs.order_by('-date_creation')
    else:
        produits_qs = produits_qs.order_by('nom')

    # Pagination
    total_count = produits_qs.count()
    try:
        per_page = int(request.GET.get('per_page', 12))
    except (TypeError, ValueError):
        per_page = 12

    paginator = Paginator(produits_qs, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))

    categories = Categorie.objects.all().order_by('nom')
    context = {
        'produits': page_obj.object_list,
        'page_obj': page_obj,
        'categories': categories,
        'search': search,
        'current_categorie': categorie_id,
        'categorie_selected_int': categorie_selected_int,
        'current_sort': sort,
        'per_page': per_page,
        'per_page_options': [12, 24, 48, 96],
        'total_count': total_count,
        'promotions': produits_qs.filter(prix_promo__isnull=False)[:12],
        'nouveautes': produits_qs.order_by('-date_creation')[:8],
        'mieux_notes': produits_qs.order_by('-date_creation')[:8],
    }
    return render(request, 'boutique/index.html', context)
def about(request):
    """Page à propos accessible à tous"""
    return render(request, 'boutique/about.html')
def custom_login(request):
    """Vue de connexion personnalisée"""
    if request.user.is_authenticated:
        return redirect('post_login_redirect')

    if request.method == 'POST':
        username = request.POST.get('username') or ''
        password = request.POST.get('password') or ''
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('post_login_redirect')
        messages.error(request, "Identifiants invalides.")

    return render(request, 'register/login.html')
@login_required
def dashboard(request):
    """Redirection intelligente après connexion"""
    if request.user.is_staff or request.user.is_superuser:
        return redirect('admin_dashboard')
    profile = getattr(request.user, 'userprofile', None)
    if getattr(profile, 'role', '').upper() == 'LIVREUR':
        return redirect('livreur_dashboard')
    return redirect('boutique')

def post_login_redirect(request):
    """Redirection après connexion"""
def register(request):
    if request.method == "POST":
        form1 = RegisterStep1Form(request.POST)
        form2 = RegisterStep2Form(request.POST, request.FILES)
        form3 = RegisterStep3Form(request.POST)

        if form1.is_valid() and form2.is_valid() and form3.is_valid():

            # 1) Création de l'utilisateur
            user = form1.save(commit=False)
            user.username = user.username.lower()
            user.save()

            # 2) Création du profil sans avatar
            profile = UserProfile.objects.create(
                user=user,
                phone=form3.cleaned_data["phone"],
                address=form3.cleaned_data["address"],
                photo=form2.cleaned_data.get("photo"),
            )

            # 3) Génération automatique avatar si aucune photo
            
            login(request, user)
            messages.success(request, "Compte créé avec succès !")
            return redirect("home")

    else:
        form1 = RegisterStep1Form()
        form2 = RegisterStep2Form()
        form3 = RegisterStep3Form()

    return render(request, "register/register.html", {
        "step1_form": form1,
        "step2_form": form2,
        "step3_form": form3,
    })
                 # ===================================================================
                 # AUTHENTIFICATION
                 # ===================================================================


def logout_view(request):
    """Vue de déconnexion simple"""
    logout(request)
    return redirect('index')


from django.views.generic.edit import CreateView
from .forms import StaffLivreurCreationForm
class StaffLivreurCreateView(CreateView):
    form_class = StaffLivreurCreationForm
    template_name = 'admin/add_staff_livreur.html'
    success_url = reverse_lazy('ajout') # Redirigez vers une liste des employés après succès

    # Assurez-vous que seul le personnel autorisé (ex: Admin/Superuser) puisse accéder à cette vue
    # Décommentez et ajustez selon vos besoins d'autorisation
    # def dispatch(self, request, *args, **kwargs):
    #     if not is_staff_admin(request.user):
    #         return redirect('home') # Redirige si non autorisé
    #     return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Le nouvel employé/livreur a été créé avec succès.")
        return super().form_valid(form)
    
# ===================================================================
# VUE POUR LE STAFF
# ===================================================================
@admin_required
def admin_dashboard(request):
    """Tableau de bord administrateur"""
    total_products = Produit.objects.count()
    total_orders = Commande.objects.count()
    total_users = User.objects.count()
    revenue = Commande.objects.aggregate(total=Sum('total'))['total'] or 0

    per_day = (
        Commande.objects
        .annotate(day=TruncDate('date_commande'))
        .values('day')
        .annotate(c=Count('id'))
        .order_by('day')
    )
    context = {
        'total_products': total_products,
        'total_orders': total_orders,
        'total_users': total_users,
        'revenue': revenue,
        'chart_days': json.dumps([d['day'].strftime('%d/%m') for d in per_day]),
        'chart_counts': json.dumps([d['c'] for d in per_day]),
        'top_products': (
            CommandeItem.objects
            .values('produit__nom')
            .annotate(qty=Sum('quantite'))
            .order_by('-qty')[:5]
        ),
        'recent_orders': Commande.objects.order_by('-date_commande')[:10],
    }
    return render(request, 'admin/dashboard.html', context)