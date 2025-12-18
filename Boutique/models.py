from django.db import models

# Create your models here.
from django.contrib.auth.models import User
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Avg
from django.utils.text import slugify


class Categorie(models.Model):
    """
    Modèle de catégorie amélioré avec support hiérarchique (Parent/Enfant) et SEO.
    """
    
    # 1. Champs de base
    nom = models.CharField(max_length=100, unique=True, verbose_name="Nom de la Catégorie" )
    # 2. ESSENTIEL POUR LE SEO ET L'URL
    slug = models.SlugField(max_length=100, unique=True, blank=True, verbose_name="Slug (URL Friendly)", help_text="Clé unique utilisée dans l'URL (ex: electronique-telephones)." )
   # 3. POUR LA HIERARCHIE (ARBORESCENCE)
    parent = models.ForeignKey(
        'self', # Référence à la classe elle-même
        null=True,
        blank=True,
        related_name='enfants', # Pour obtenir les sous-catégories
        on_delete=models.CASCADE,
        verbose_name="Catégorie Parent"
    )
    
    # 4. Description et Affichage
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Description détaillée (SEO)"
    )
    
    icon = models.CharField(
        max_length=50,
        default='fas fa-folder',
        verbose_name="Icône (Classe FontAwesome)"
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name="Est active"
    )
    
    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"
        ordering = ['nom']

    def __str__(self):
        # Affichage plus clair dans l'administration
        if self.parent:
            return f"{self.parent.nom} > {self.nom}"
        return self.nom

    def save(self, *args, **kwargs):
        """Génère le slug si le champ est vide ou s'il s'agit d'un nouvel enregistrement."""
        if not self.slug or not self.pk:
            # Création du slug à partir du nom
            self.slug = slugify(self.nom)
            
        super().save(*args, **kwargs)

    # ----------------------------------------------------
    # Propriété Utile : Chemin complet
    # ----------------------------------------------------
    @property
    def full_path(self):
        """Retourne le chemin complet de la catégorie (ex: Électronique/Téléphones)."""
        if self.parent:
            return f"{self.parent.full_path}/{self.nom}"
        return self.nom


class Produit(models.Model):
    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    prix = models.DecimalField(max_digits=10, decimal_places=0)  
    prix_promo = models.DecimalField(max_digits=10, decimal_places=0, blank=True, null=True)
    image = models.ImageField(upload_to='produits/', blank=True, null=True)
    categories = models.ManyToManyField(Categorie, related_name='produits')
    date_creation = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.nom

    @property
    def note_moyenne(self):
        return self.notes.aggregate(Avg('valeur'))['valeur__avg'] or 0
    
    @property
    def nombre_notes(self):
        return self.notes.count()

    @property
    def est_populaire(self):
        return self.nombre_notes >= 5 and self.note_moyenne >= 4

    @property
    def categorie_principale(self):
        return self.categories.first()


class RoleChoices(models.TextChoices):
    CLIENT = 'CLIENT', 'Client'
    LIVREUR = 'LIVREUR', 'Livreur'
    STAFF = 'STAFF', 'Staff'


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    user_type = models.CharField(max_length=20, default='CLIENT', editable=False)
    phone = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    photo = models.ImageField(upload_to='profiles/', blank=True, null=True)
    role = models.CharField(max_length=20, choices=RoleChoices.choices, default=RoleChoices.CLIENT)

    def __str__(self):
        return f"{self.user.username} - {self.user_type}"


class Note(models.Model):
    produit = models.ForeignKey('Produit', on_delete=models.CASCADE, related_name='notes')
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    valeur = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    commentaire = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('produit', 'user')  # Un utilisateur ne peut noter qu'une fois


class Commande(models.Model):
    STATUT_CHOICES = [
        ('EN_ATTENTE', 'En attente'),
        ('EN_COURS', 'En cours'),
        ('LIVREE', 'Livrée'),
        ('ANNULEE', 'Annulée'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date_commande = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='EN_ATTENTE')
    total = models.DecimalField(max_digits=10, decimal_places=2)

    # Champs GPS
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    adresse_gps = models.TextField(blank=True, null=True, help_text="Adresse formatée via géocodage inverse")
    
    # Position du livreur (mise à jour en temps réel)
    latitude_livreur = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude_livreur = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    derniere_maj_position = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Commande #{self.id} - {self.user.username}"

    @property
    def position_client(self):
        if self.latitude_client and self.longitude_client:
            return {
                'lat': float(self.latitude_client),
                'lng': float(self.longitude_client),
                'address': self.adresse_gps_client or ''
            }
        return None
    
    @property
    def position_livreur(self):
        if self.latitude_livreur and self.longitude_livreur:
            return {
                'lat': float(self.latitude_livreur),
                'lng': float(self.longitude_livreur),
                'last_update': self.derniere_maj_position
            }
        return None

class CommandeItem(models.Model):
    commande = models.ForeignKey(Commande, related_name='items', on_delete=models.CASCADE)
    produit = models.ForeignKey('Produit', on_delete=models.CASCADE)
    quantite = models.PositiveIntegerField(default=1)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantite}x {self.produit.nom}"

class PanierItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='panier_items')
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    quantite = models.PositiveIntegerField(default=1)
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'produit')  # Un utilisateur ne peut avoir qu'un seul item par produit
        verbose_name = "Article du panier"
        verbose_name_plural = "Articles du panier"

    def __str__(self):
        return f"{self.user.username} - {self.produit.nom} ({self.quantite})"

    def prix_total(self):
        """Calcule le prix total pour cet item (quantité × prix)"""
        prix = self.produit.prix_promo if self.produit.prix_promo else self.produit.prix
        return prix * self.quantite

    def prix_unitaire(self):
        """Retourne le prix unitaire (avec promo si applicable)"""
        return self.produit.prix_promo if self.produit.prix_promo else self.produit.prix

class Adresse(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='adresses')
    nom = models.CharField(max_length=100, blank=True)  # ex: Domicile, Bureau
    destinataire = models.CharField(max_length=150)
    ligne1 = models.CharField(max_length=255)
    ligne2 = models.CharField(max_length=255, blank=True)
    ville = models.CharField(max_length=120)
    region = models.CharField(max_length=120, blank=True)
    code_postal = models.CharField(max_length=20, blank=True)
    pays = models.CharField(max_length=120, default='Sénégal')
    telephone = models.CharField(max_length=30, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Adresse"
        verbose_name_plural = "Adresses"
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        label = self.nom or self.destinataire
        return f"{label} - {self.ligne1}, {self.ville}"
class Avis(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    valeur = models.IntegerField(default=5) # La note (ex: 1 à 5)
    commentaire = models.TextField(blank=True)
    date_avis = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.produit.nom} - {self.valeur}/5'