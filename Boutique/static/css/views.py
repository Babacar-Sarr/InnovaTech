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
from boutique.forms import (
    AdminProfileForm, AdresseForm, CategorieForm, DelivererCreateForm, 
    DelivererProfileForm, DelivererProfileUpdateForm, DelivererUserUpdateForm, 
    ProduitForm, UserUpdateForm,RegisterStep1Form, RegisterStep2Form, RegisterStep3Form
)
from .models import (
    Produit, Categorie, Commande, CommandeItem, PanierItem, UserProfile, 
    Note, Adresse, RoleChoices
)
from .constants import FRAIS_LIVRAISON_DEFAUT

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
    return render(request, 'boutique/boutique.html', context)

def about(request):
    """Page à propos accessible à tous"""
    return render(request, 'boutique/about.html')
def generate_avatar(initials, user_id):
    """ Génère un avatar PNG basé sur les initiales """
    img_size = (300, 300)
    background_color = "#1D4ED8"  # bleu moderne
    text_color = "white"

    img = Image.new("RGB", img_size, background_color)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 130)
    except:
        font = ImageFont.load_default()

    w, h = draw.textsize(initials, font=font)
    position = ((img_size[0] - w) / 2, (img_size[1] - h) / 2)

    draw.text(position, initials, fill=text_color, font=font)

    filename = f"avatar_{user_id}.png"
    filepath = os.path.join(settings.MEDIA_ROOT, "avatars", filename)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    img.save(filepath)

    return f"avatars/{filename}"


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
            if not profile.photo:
                initials = (user.first_name[:1] + user.last_name[:1]).upper()
                avatar_path = generate_avatar(initials, user.id)
                profile.avatar = avatar_path
                profile.save()

            login(request, user)
            messages.success(request, "Compte créé avec succès !")
            return redirect("home")

    else:
        form1 = RegisterStep1Form()
        form2 = RegisterStep2Form()
        form3 = RegisterStep3Form()

    return render(request, "registration/register.html", {
        "step1_form": form1,
        "step2_form": form2,
        "step3_form": form3,
    })

# ===================================================================
# AUTHENTIFICATION
# ===================================================================

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

    return render(request, 'registration/login.html')

def logout_view(request):
    """Vue de déconnexion simple"""
    logout(request)
    return redirect('home')

def admin_logout(request):
    """Déconnexion pour les admins"""
    logout(request)
    messages.success(request, "Vous avez été déconnecté avec succès.")
    return redirect('login')

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
    return redirect('dashboard')

class CustomLoginView(LoginView):
    """Vue de connexion Django personnalisée"""
    template_name = 'registration/login.html'
    redirect_authenticated_user = True
    success_url = reverse_lazy('home')
    
    def get_success_url(self):
        return self.success_url

@method_decorator([login_required, user_passes_test(lambda u: u.is_staff)], name='dispatch')
class AdminPasswordChangeView(PasswordChangeView):
    """Vue de changement de mot de passe pour admin"""
    template_name = 'adminpanel/change_password.html'
    success_url = '/admin-panel/profile/'
    
    def get_success_url(self):
        messages.success(self.request, 'Mot de passe modifié avec succès.')
        return super().get_success_url()

# ===================================================================
# VUES CLIENT
# ===================================================================

@login_required
def profile(request):
    profile_obj, _ = UserProfile.objects.get_or_create(user=request.user)
    adresses = Adresse.objects.filter(user=request.user)
    address_form = AdresseForm()

    if request.method == 'POST':
        section = request.POST.get('_section', '')

        # ✔️ AJOUT D’UNE ADRESSE
        if section == 'adresse_create':
            form = AdresseForm(request.POST)
            if form.is_valid():
                adr = form.save(commit=False)
                adr.user = request.user

                # première adresse = adresse par défaut
                if not adresses.exists():
                    adr.is_default = True

                adr.save()
                messages.success(request, "Adresse ajoutée avec succès.")
                return redirect('profile')

            address_form = form

        # ✔️ MODIFICATION D’UNE ADRESSE
        elif section == 'adresse_update':
            adr_id = request.POST.get('adresse_id')
            adr = get_object_or_404(Adresse, id=adr_id, user=request.user)

            form = AdresseForm(request.POST, instance=adr)
            if form.is_valid():
                form.save()
                messages.success(request, "Adresse modifiée avec succès.")
                return redirect('profile')

            address_form = form

        # ✔️ Mise à jour photo de profil
        elif 'photo' in request.FILES:
            profile_obj.photo = request.FILES['photo']
            profile_obj.save(update_fields=['photo'])
            messages.success(request, "Photo mise à jour.")
            return redirect('profile')

        # ✔️ Mise à jour infos utilisateur
        elif 'update_info' in request.POST:
            request.user.first_name = request.POST.get('first_name')
            request.user.last_name = request.POST.get('last_name')
            profile_obj.phone = request.POST.get('phone')

            request.user.save()
            profile_obj.save()

            messages.success(request, "Informations mises à jour.")
            return redirect('profile')

    recent_orders = Commande.objects.filter(user=request.user).order_by('-id')[:5]

    return render(request, 'boutique/profile.html', {
        'profile': profile_obj,
        'adresses': adresses,
        'address_form': address_form,
        'recent_orders': recent_orders,
    })

@login_required
def mes_commandes(request):
    commandes = (
        Commande.objects
        .filter(user=request.user)
        .order_by('-date_commande')
        .prefetch_related('items__produit')
    )
    return render(request, "boutique/mes_commandes.html", {"commandes": commandes})


def commande_items_json(request, id):
    commande = get_object_or_404(Commande, id=id)

    items = [{
        "produit": item.produit.nom,
        "quantite": item.quantite,
        "prix_unitaire": float(item.prix_unitaire),
        "sous_total": float(item.quantite * item.prix_unitaire)
    } for item in commande.items.all()]

    return JsonResponse({"items": items})
@login_required
def commande_items_api(request, commande_id):
    commande = Commande.objects.get(id=commande_id, user=request.user)
    items = [
        {
            "produit": item.produit.nom,
            "quantite": item.quantite,
            "prix": float(item.prix_unitaire),
            "sous_total": float(item.sous_total())
        }
        for item in commande.items.all()
    ]
    return JsonResponse({"items": items})

@login_required
def change_password(request):
    """Changement de mot de passe utilisateur"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Mot de passe changé avec succès !')
            return redirect('profile')
        else:
            messages.error(request, 'Erreur dans le formulaire.')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'boutique/change_password.html', {'form': form})

@login_required
@require_POST
def noter_produit(request, produit_id):
    """Notation d'un produit par l'utilisateur"""
    produit = get_object_or_404(Produit, id=produit_id)
    try:
        valeur = int(request.POST.get('valeur', 0))
        commentaire = request.POST.get('commentaire', '')
        note, _ = Note.objects.update_or_create(
            produit=produit, user=request.user,
            defaults={'valeur': valeur, 'commentaire': commentaire}
        )
        messages.success(request, 'Note enregistrée.')
    except Exception:
        messages.error(request, 'Erreur lors de la notation.')
    return redirect('boutique')

# ===================================================================
# GESTION DU PANIER
# ===================================================================

@require_POST
def ajouter_au_panier(request, produit_id):
    """Ajouter un produit au panier"""
    produit = get_object_or_404(Produit, pk=produit_id)

    if request.user.is_authenticated:
        item, created = PanierItem.objects.get_or_create(
            user=request.user,
            produit=produit,
            defaults={'quantite': 1}
        )
        if not created:
            item.quantite += 1
            item.save(update_fields=['quantite'])
    else:
        cart = request.session.get('panier', {})
        key = str(produit_id)
        qty = int(cart.get(key, {}).get('quantite', 0)) + 1
        cart[key] = {'quantite': qty}
        request.session['panier'] = cart
        request.session.modified = True

    count = _get_cart_count(request)
    return JsonResponse({
        'success': True,
        'message': f'{produit.nom} ajouté au panier',
        'cart_count': count,
        'count': count
    }, status=200)

def cart_count_ajax(request):
    """Récupération AJAX du nombre d'articles dans le panier"""
    count = _get_cart_count(request)
    return JsonResponse({
        'success': True,
        'cart_count': count,
        'count': count
    }, status=200)

@login_required
def voir_panier(request):
    """Affichage du contenu du panier"""
    items_qs = PanierItem.objects.select_related('produit').filter(user=request.user)
    items = []
    total = 0
    for it in items_qs:
        pu = _unit_price(it.produit)
        sous_total = pu * it.quantite
        total += sous_total
        it.prix_total = sous_total
        items.append(it)

    context = {
        'items': items,
        'total': total,
        'shipping': 0,
        'cart_count': sum(i.quantite for i in items),
    }
    return render(request, 'boutique/panier.html', context)

@login_required
def retirer_du_panier(request, item_id):
    """Retirer un article du panier"""
    item = get_object_or_404(PanierItem, id=item_id, user=request.user)
    nom_produit = item.produit.nom
    item.delete()
    
    messages.success(request, f'{nom_produit} retiré du panier.')
    return redirect('panier')

@login_required
@require_POST
def modifier_quantite(request):
    """Modifier la quantité d'un article dans le panier"""
    try:
        item_id = int(request.POST.get('item_id'))
        nouvelle_quantite = int(request.POST.get('qty'))
        
        item = get_object_or_404(PanierItem, id=item_id, user=request.user)
        
        if nouvelle_quantite <= 0:
            nom_produit = item.produit.nom
            item.delete()
            messages.info(request, f'{nom_produit} retiré du panier.')
        else:
            item.quantite = nouvelle_quantite
            item.save()
            messages.success(request, 'Quantité mise à jour.')
            
    except (ValueError, TypeError):
        messages.error(request, 'Quantité invalide.')
    except Exception as e:
        messages.error(request, 'Erreur lors de la modification.')
    
    return redirect('panier')

@login_required
@require_POST
@transaction.atomic
def confirmer_commande(request):
    """Confirmation et création d'une commande"""
    items = list(PanierItem.objects.select_related('produit').filter(user=request.user))
    if not items:
        messages.error(request, "Votre panier est vide.")
        return redirect('panier')

    adresse_defaut = Adresse.objects.filter(user=request.user, is_default=True).first()
    total = sum(_unit_price(it.produit) * it.quantite for it in items)

    # Récupération des données GPS
    latitude = request.POST.get('latitude')
    longitude = request.POST.get('longitude')
    adresse_gps = request.POST.get('adresse_gps')

    # Création de la commande
    cmd_kwargs = {'user': request.user}
    if hasattr(Commande, 'statut'):
        cmd_kwargs['statut'] = _pending_choice_for_statut()
    elif hasattr(Commande, 'status'):
        cmd_kwargs['status'] = 'pending'
    if hasattr(Commande, 'total'):
        cmd_kwargs['total'] = total
    if adresse_defaut and hasattr(Commande, 'adresse'):
        cmd_kwargs['adresse'] = adresse_defaut
    if adresse_defaut and hasattr(Commande, 'adresse_livraison'):
        cmd_kwargs['adresse_livraison'] = adresse_defaut
    
    # Ajout des coordonnées GPS
    if latitude and longitude:
        cmd_kwargs['latitude'] = float(latitude)
        cmd_kwargs['longitude'] = float(longitude)
    if adresse_gps:
        cmd_kwargs['adresse_gps'] = adresse_gps

    commande = Commande.objects.create(**cmd_kwargs)
    envoyer_mail_statut_commande(commande)

    # Création des lignes de commande
    for it in items:
        pu = _unit_price(it.produit)
        ci_kwargs = {'commande': commande, 'produit': it.produit, 'quantite': it.quantite}
        if hasattr(CommandeItem, 'prix_unitaire'):
            ci_kwargs['prix_unitaire'] = pu
        elif hasattr(CommandeItem, 'prix'):
            ci_kwargs['prix'] = pu
        CommandeItem.objects.create(**ci_kwargs)

    # Vider le panier
    PanierItem.objects.filter(user=request.user).delete()
    if 'panier' in request.session:
        request.session['panier'] = {}
        request.session.modified = True

    messages.success(request, "Commande confirmée avec localisation. Merci pour votre achat !")
    return redirect('mes_commandes')

# ===================================================================
# GESTION DES ADRESSES
# ===================================================================

@login_required
@require_POST
def adresse_defaut(request, pk):
    """Définir une adresse par défaut"""
    adr = get_object_or_404(Adresse, pk=pk, user=request.user)
    Adresse.objects.filter(user=request.user, is_default=True).update(is_default=False)
    adr.is_default = True
    adr.save(update_fields=['is_default'])
    messages.success(request, "Adresse définie par défaut.")
    return HttpResponseRedirect(reverse('profile'))

@login_required
@require_http_methods(['POST'])
def adresse_supprimer(request, pk):
    """Supprimer une adresse"""
    adr = get_object_or_404(Adresse, pk=pk, user=request.user)
    was_default = adr.is_default
    adr.delete()
    if was_default:
        reste = Adresse.objects.filter(user=request.user).order_by('-created_at').first()
        if reste:
            reste.is_default = True
            reste.save(update_fields=['is_default'])
    messages.success(request, "Adresse supprimée.")
    return HttpResponseRedirect(reverse('profile'))

@login_required
@require_http_methods(['POST'])
def adresse_modifier(request, pk):
    """Modifier une adresse"""
    adr = get_object_or_404(Adresse, pk=pk, user=request.user)
    form = AdresseForm(request.POST, instance=adr)
    if form.is_valid():
        form.save()
        messages.success(request, "Adresse mise à jour.")
    else:
        messages.error(request, "Vérifiez le formulaire d'adresse.")
    return HttpResponseRedirect(reverse('profile'))

# ===================================================================
# VUES LIVREUR
# ===================================================================

@login_required
def livreur_profile(request):
    """Profil du livreur"""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = None
    
    # Calculer les statistiques du livreur
    orders = _livreur_orders_queryset(request.user)
    stats = _livreur_stats(orders)
    
    if request.method == 'POST':
        uform = UserUpdateForm(request.POST, instance=request.user)
        
        if profile:
            pform = DelivererProfileForm(request.POST, request.FILES, instance=profile)
        else:
            pform = DelivererProfileForm(request.POST, request.FILES)
        
        if uform.is_valid() and pform.is_valid():
            # Sauvegarder l'utilisateur
            uform.save()
            
            # Sauvegarder le profil livreur
            profile_instance = pform.save(commit=False)
            profile_instance.user = request.user
            profile_instance.save()
            
            messages.success(request, 'Votre profil a été mis à jour avec succès.')
            return redirect('livreur_profile')
        else:
            messages.error(request, 'Veuillez corriger les erreurs ci-dessous.')
    else:
        uform = UserUpdateForm(instance=request.user)
        pform = DelivererProfileForm(instance=profile)
    
    context = {
        'uform': uform,
        'pform': pform,
        'profile': profile,
        'stats': stats,
        'active_tab': 'profile'
    }
    return render(request, 'livreur/livreur_profile.html', context)

@login_required
def livreur_dashboard(request):
    """Tableau de bord du livreur"""
    orders = _livreur_orders_queryset(request.user)
    stats = _livreur_stats(orders)
    
    # Commandes récentes pour le dashboard
    recent_orders = orders[:5]
    
    context = {
        'orders': recent_orders, 
        'stats': stats,
        'recent_orders': recent_orders,
        'active_tab': 'dashboard'
    }
    return render(request, 'livreur/dashboard.html', context)

@login_required
def livreur_orders(request):
    """Liste complète des commandes pour le livreur"""
    orders = _livreur_orders_queryset(request.user)
    stats = _livreur_stats(orders)
    
    # Filtrage par statut si nécessaire
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(statut=status_filter)
    
    context = {
        'orders': orders,
        'stats': stats,
        'status_filter': status_filter,
        'active_tab': 'orders'
    }
    return render(request, 'livreur/orders.html', context)

@login_required
def livreur_stats(request):
    """Statistiques détaillées du livreur"""
    orders = _livreur_orders_queryset(request.user)
    stats = _livreur_stats(orders)
    
    # Statistiques par mois avec revenus
    from django.db.models import Count
    from django.db.models.functions import TruncMonth
    from decimal import Decimal
    
    FRAIS_LIVRAISON = Decimal('1000')
    
    monthly_stats = (
        orders.filter(statut='LIVREE')  # Seulement les commandes livrées
        .annotate(month=TruncMonth('date_commande'))
        .values('month')
        .annotate(
            count=Count('id'),
        )
        .order_by('month')
    )
    
    # Ajouter les revenus mensuels
    for month_data in monthly_stats:
        month_data['revenue'] = month_data['count'] * FRAIS_LIVRAISON
    
    context = {
        'stats': stats,
        'monthly_stats': monthly_stats,
        'orders_count': orders.count(),
        'active_tab': 'stats'
    }
    return render(request, 'livreur/stats.html', context)

@login_required
def livreur_map(request):
    """Carte des livraisons"""
    orders = _livreur_orders_queryset(request.user).filter(
        latitude__isnull=False, 
        longitude__isnull=False
    )
    stats = _livreur_stats(orders)
    
    context = {
        'orders': orders,
        'stats': stats,
        'active_tab': 'map'
    }
    return render(request, 'livreur/map.html', context)

@login_required
@user_passes_test(is_livreur)
def livreur_order_detail(request, pk):
    """Détail d'une commande pour le livreur"""
    order = get_object_or_404(Commande.objects.select_related('user'), pk=pk)
    items = list(CommandeItem.objects.select_related('produit').filter(commande=order))
    for it in items:
        unit = getattr(it, 'prix_unitaire', None) or getattr(it, 'prix', None) or 0
        qty = getattr(it, 'quantite', 0) or 0
        it.unit_price = unit
        it.line_total = unit * qty

    return render(request, 'livreur/order_detail.html', {'order': order, 'items': items})

@login_required
@user_passes_test(is_livreur)
@require_POST
def livreur_order_accept(request, pk):
    """Accepter une commande"""
    order = get_object_or_404(Commande, pk=pk)

    if hasattr(order, 'livreur') and not getattr(order, 'livreur', None):
        order.livreur = request.user

    if getattr(order, 'statut', None) == 'EN_ATTENTE':
        order.statut = 'EN_COURS'
        update_fields = ['statut']
        if hasattr(order, 'livreur'):
            update_fields.append('livreur')
        order.save(update_fields=update_fields)
        messages.success(request, f"Commande #{order.id} acceptée.")
    else:
        messages.info(request, f"Commande #{order.id} déjà {order.statut or 'traitée'}.")

    return redirect(request.POST.get('next') or 'livreur_orders')

@login_required
@user_passes_test(is_livreur)
@require_POST
def livreur_order_update_status(request, pk):
    """Mettre à jour le statut d'une commande"""
    order = get_object_or_404(Commande, pk=pk)
    action = request.POST.get('action', '')
    
    current_status = getattr(order, 'statut', None)
    
    if action == 'accept' and current_status == 'EN_ATTENTE':
        # Accepter la commande
        if hasattr(order, 'livreur') and not getattr(order, 'livreur', None):
            order.livreur = request.user
        
        order.statut = 'EN_COURS'
        update_fields = ['statut']
        if hasattr(order, 'livreur'):
            update_fields.append('livreur')
        
        order.save(update_fields=update_fields)
        messages.success(request, f"Commande #{order.id} acceptée.")
        
    elif action == 'complete' and current_status == 'EN_COURS':
        # Marquer comme livrée
        order.statut = 'LIVREE'
        update_fields = ['statut']
        
        # Ajouter la date de livraison si le champ existe
        if hasattr(order, 'date_livraison'):
            order.date_livraison = timezone.now()
            update_fields.append('date_livraison')
        
        order.save(update_fields=update_fields)
        messages.success(request, f"Commande #{order.id} marquée comme livrée.")
        
    else:
        messages.warning(request, f"Action '{action}' non autorisée pour la commande #{order.id} (statut: {current_status})")

    return redirect(request.POST.get('next') or 'livreur_orders')

# ===================================================================
# VUES ADMIN
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
    return render(request, 'adminpanel/dashboard.html', context)

@admin_required
def admin_profile(request):
    """Profil administrateur"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == "POST":
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = AdminProfileForm(request.POST, request.FILES, instance=profile)
        
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Profil mis à jour avec succès!")
            return redirect("admin_profile")
        else:
            messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = AdminProfileForm(instance=profile)
    
    context = {
        "user_form": user_form,
        "profile_form": profile_form,
        "profile": profile,
    }
    return render(request, "adminpanel/profile.html", context)

@admin_required
def admin_products(request):
    """Gestion des produits"""
    qs = Produit.objects.all().order_by('-date_creation')
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'adminpanel/products.html', {
        'produits': page_obj.object_list,
        'page_obj': page_obj,
        'total_count': qs.count(),
    })

@admin_required
def admin_categories(request):
    """Gestion des catégories"""
    categories = Categorie.objects.all().order_by('nom')
    return render(request, 'adminpanel/categories.html', {'categories': categories})

# CRUD Produits
@staff_required
def admin_product_create(request):
    """Création d'un produit"""
    form = ProduitForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Produit créé avec succès.")
        return redirect('admin_products')
    return render(request, 'adminpanel/product_form.html', {'form': form, 'mode': 'create'})

@staff_required
def admin_product_update(request, pk):
    """Modification d'un produit"""
    produit = get_object_or_404(Produit, pk=pk)
    form = ProduitForm(request.POST or None, request.FILES or None, instance=produit)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Produit modifié avec succès.")
        return redirect('admin_products')
    return render(request, 'adminpanel/product_form.html', {'form': form, 'mode': 'update', 'produit': produit})

@staff_required
def admin_product_delete(request, pk):
    """Suppression d'un produit"""
    produit = get_object_or_404(Produit, pk=pk)
    if request.method == 'POST':
        produit.delete()
        messages.success(request, "Produit supprimé.")
        return redirect('admin_products')
    return render(request, 'adminpanel/product_confirm_delete.html', {'produit': produit})

# CRUD Catégories
@staff_required
def admin_category_create(request):
    """Création d'une catégorie"""
    form = CategorieForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Catégorie créée avec succès.")
        return redirect('admin_categories')
    return render(request, 'adminpanel/category_form.html', {'form': form, 'mode': 'create'})

@staff_required
def admin_category_update(request, pk):
    """Modification d'une catégorie"""
    categorie = get_object_or_404(Categorie, pk=pk)
    form = CategorieForm(request.POST or None, instance=categorie)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Catégorie modifiée avec succès.")
        return redirect('admin_categories')
    return render(request, 'adminpanel/category_form.html', {'form': form, 'mode': 'update', 'categorie': categorie})

@staff_required
def admin_category_delete(request, pk):
    """Suppression d'une catégorie"""
    categorie = get_object_or_404(Categorie, pk=pk)
    if request.method == 'POST':
        categorie.delete()
        messages.success(request, "Catégorie supprimée.")
        return redirect('admin_categories')
    return render(request, 'adminpanel/category_confirm_delete.html', {'categorie': categorie})

# Gestion des livreurs
@admin_required
def admin_livreurs_list(request):
    """Liste des livreurs"""
    q = request.GET.get('q', '')
    qs = UserProfile.objects.select_related('user').filter(role=RoleChoices.LIVREUR)
    if q:
        qs = qs.filter(Q(user__username__icontains=q) | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(phone__icontains=q))
    return render(request, 'adminpanel/deliverers.html', {'deliverers': qs, 'q': q})

@admin_required
def admin_livreurs_create(request):
    """Création d'un livreur"""
    if request.method == 'POST':
        form = DelivererCreateForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Livreur {user.username} créé.")
            return redirect('admin_livreurs_list')
    else:
        form = DelivererCreateForm()
    return render(request, 'adminpanel/deliverer_form.html', {'form': form, 'mode': 'create'})

@admin_required
def admin_livreurs_edit(request, user_id):
    """Modification d'un livreur"""
    user = get_object_or_404(User, pk=user_id)
    profile = get_object_or_404(UserProfile, user=user, role=RoleChoices.LIVREUR)
    if request.method == 'POST':
        uform = DelivererUserUpdateForm(request.POST, instance=user)
        pform = DelivererProfileUpdateForm(request.POST, request.FILES, instance=profile)
        if uform.is_valid() and pform.is_valid():
            uform.save()
            pform.save()
            messages.success(request, "Livreur mis à jour.")
            return redirect('admin_livreurs_list')
    else:
        uform = DelivererUserUpdateForm(instance=user)
        pform = DelivererProfileUpdateForm(instance=profile)
    return render(request, 'adminpanel/deliverer_form.html', {'uform': uform, 'pform': pform, 'mode': 'update', 'deliverer': user})

@admin_required
def admin_livreurs_toggle_active(request, user_id):
    """Activer/désactiver un livreur"""
    user = get_object_or_404(User, pk=user_id)
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    messages.success(request, f"Statut de {user.username} mis à jour.")
    return redirect('admin_livreurs_list')

# Gestion des clients
@admin_required
def admin_clients_list(request):
    """Liste des clients"""
    clients_list = User.objects.filter(is_staff=False).select_related('userprofile').order_by('-date_joined')
    
    search = request.GET.get('q')
    if search:
        clients_list = clients_list.filter(
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )
    
    paginator = Paginator(clients_list, 20)
    page_number = request.GET.get('page')
    clients = paginator.get_page(page_number)
    
    context = {
        'clients': clients,
        'search': search,
        'total_clients': clients_list.count(),
    }
    return render(request, 'adminpanel/clients_list.html', context)

@admin_required
def admin_client_toggle_active(request, user_id):
    """Activer/désactiver un client"""
    client = get_object_or_404(User, id=user_id, is_staff=False)
    client.is_active = not client.is_active
    client.save()
    
    status = "activé" if client.is_active else "désactivé"
    messages.success(request, f"Client {client.username} {status}.")
    return redirect('admin_clients_list')

@admin_required
def admin_client_detail(request, user_id):
    """Détail d'un client"""
    client = get_object_or_404(User, id=user_id, is_staff=False)
    profile = getattr(client, 'userprofile', None)
    
    context = {
        'client': client,
        'profile': profile,
    }
    return render(request, 'adminpanel/client_detail.html', context)

# Gestion des commandes
@staff_required
def admin_orders_list(request):
    """Liste des commandes pour l'admin"""
    q = request.GET.get('q', '')
    status = request.GET.get('status')

    orders = Commande.objects.select_related('user').order_by('-id')
    if q:
        orders = orders.filter(
            Q(id__icontains=q) |
            Q(user__username__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q)
        )
    if status:
        orders = orders.filter(statut=status)

    stats = {
        'all': Commande.objects.count(),
        'pending': Commande.objects.filter(statut='EN_ATTENTE').count(),
        'in_progress': Commande.objects.filter(statut='EN_COURS').count(),
        'completed': Commande.objects.filter(statut='LIVREE').count(),
        'revenue': Commande.objects.filter(statut='LIVREE').aggregate(Sum('total'))['total__sum'] or 0,
    }
    return render(request, 'adminpanel/orders_list.html', {'orders': orders, 'stats': stats, 'q': q})

@staff_required
def admin_order_detail(request, pk):
    """Détail d'une commande pour l'admin"""
    order = get_object_or_404(Commande.objects.select_related('user'), pk=pk)
    items = list(CommandeItem.objects.select_related('produit').filter(commande=order))

    for it in items:
        unit = getattr(it, 'prix_unitaire', None)
        if unit is None:
            unit = getattr(it, 'prix', None)
        if unit is None:
            unit = 0
        it.unit_price = unit
        it.line_total = unit * (getattr(it, 'quantite', 0) or 0)

    return render(request, 'adminpanel/order_detail.html', {'order': order, 'items': items})

@login_required
def livreur_change_password(request):
    """Changement de mot de passe pour livreur"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Mot de passe changé avec succès !')
            return redirect('livreur_profile')
        else:
            messages.error(request, 'Erreur dans le formulaire.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'livreur/change_password.html', {'form': form})