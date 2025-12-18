from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import Produit, Categorie, UserProfile, RoleChoices, Adresse
from django.utils.text import slugify

User = get_user_model()
class RegisterStep1Form(UserCreationForm):
    first_name = forms.CharField(max_length=50, required=True, label="Prénom")
    last_name = forms.CharField(max_length=50, required=True, label="Nom")

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name',
                  'email', 'password1', 'password2']

# ÉTAPE 2
class RegisterStep2Form(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['photo']
        widgets = {
            'photo': forms.FileInput(),
            
        }

# ÉTAPE 3
class RegisterStep3Form(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone', 'address']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }
class CustomUserCreationForm(UserCreationForm):
     phone = forms.CharField(max_length=15, required=False, label='Téléphone') 
     address = forms.CharField(widget=forms.Textarea, required=False, label='Adresse') 
     class Meta: 
        model = User 
        fields = ('username', 'email', 'password1', 'password2', 'phone', 'address') 
        def save(self, commit=True): 
            user = super().save(commit=False) 
            user.email = self.cleaned_data.get('email') 
            if commit: 
                user.save() 
                UserProfile.objects.get_or_create( user=user, defaults={ 'phone': self.cleaned_data.get('phone'), 'address': self.cleaned_data.get('address'), } )
                return user

class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone', 'address', 'photo']
        widgets = {'address': forms.Textarea(attrs={'rows': 3})}

class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            cls = f.widget.attrs.get('class', '')
            if isinstance(f.widget, (forms.CheckboxInput,)):
                f.widget.attrs['class'] = (cls + ' form-check-input').strip()
            elif isinstance(f.widget, (forms.Select,)):
                f.widget.attrs['class'] = (cls + ' form-select').strip()
            else:
                f.widget.attrs['class'] = (cls + ' form-control').strip()

class ProduitForm(BootstrapModelForm):
    class Meta:
        model = Produit
        fields = ['nom', 'description', 'prix', 'prix_promo', 'image', 'categories']
        labels = {
            'nom': 'Nom',
            'description': 'Description',
            'prix': 'Prix (F)',
            'prix_promo': 'Prix promo (F)',
            'image': 'Image',
            'categories': 'Catégories',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'prix': forms.NumberInput(attrs={'min': 0, 'step': 1, 'class': 'form-control'}),
            'prix_promo': forms.NumberInput(attrs={'min': 0, 'step': 1, 'class': 'form-control'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'categories': forms.SelectMultiple(attrs={'size': 6, 'class': 'form-select'}),
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ordonner les catégories par nom
        self.fields['categories'].queryset = Categorie.objects.all().order_by('nom')

    def clean(self):
        cleaned = super().clean()
        prix = cleaned.get('prix')
        prix_promo = cleaned.get('prix_promo')
        if prix is not None and prix < 0:
            self.add_error('prix', 'Le prix doit être positif.')
        if prix_promo is not None:
            if prix_promo < 0:
                self.add_error('prix_promo', 'Le prix promo doit être positif.')
            if prix is not None and prix_promo > prix:
                self.add_error('prix_promo', 'Le prix promo ne peut pas dépasser le prix.')
        return cleaned

# forms.py

from django import forms
from .models import Categorie # Assurez-vous d'importer votre modèle correctement

class CategorieForm(forms.ModelForm):
    """
    Formulaire pour la création et la modification d'une catégorie.
    Utilise ModelForm pour simplifier la création des champs.
    """
    
    # Champ parent : Utilise ModelChoiceField pour une meilleure sélection
    # On exclut la catégorie en cours d'édition (instance) pour éviter les boucles infinies.
    parent = forms.ModelChoiceField(
        queryset=Categorie.objects.all().order_by('nom'),
        required=False, # Une catégorie n'a pas besoin d'avoir de parent
        empty_label="-- Catégorie Principale --",
        label="Catégorie Parent"
    )

    class Meta:
        model = Categorie
        fields = [
            'nom', 
            'slug', 
            'parent', 
            'description', 
            'icon', 
            'is_active'
        ]
        
        # Widgets personnalisés pour améliorer l'apparence
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Téléphones & Smartphones'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Laissez vide pour générer automatiquement'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Description détaillée pour le SEO...'}),
            'icon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: fas fa-mobile-alt'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        
    def __init__(self, *args, **kwargs):
        """Initialisation personnalisée pour exclure la catégorie elle-même de la liste 'parent'."""
        super().__init__(*args, **kwargs)
        
        # Exclure l'instance actuelle (si c'est une modification) de la liste des parents possibles
        if self.instance.pk:
            # Récupère l'ID de l'instance en cours d'édition
            current_id = self.instance.pk
            
            # Filtre le queryset du champ 'parent' pour exclure l'instance en cours
            self.fields['parent'].queryset = Categorie.objects.exclude(pk=current_id).order_by('nom')
        
        # Appliquer les classes Bootstrap à tous les champs (sauf le Checkbox)
        for name, field in self.fields.items():
            if name != 'is_active' and not isinstance(field.widget, forms.Select):
                 # Les widgets text/textarea/number/etc.
                field.widget.attrs.setdefault('class', 'form-control')
            elif isinstance(field.widget, forms.Select):
                # Le widget Select pour le parent
                field.widget.attrs.setdefault('class', 'form-select')


    def clean_slug(self):
        """
        Nettoie et assure que le slug est généré/mis à jour s'il n'est pas fourni.
        """
        slug = self.cleaned_data.get('slug')
        nom = self.cleaned_data.get('nom')
        
        # Si le slug est vide, on le génère à partir du nom
        if not slug and nom:
            # Utilisation de slugify du modèle (ou de django.utils.text.slugify)
            slug = slugify(nom)
            
        return slug

    def clean(self):
        """
        Validation personnalisée pour vérifier qu'une catégorie ne peut pas être son propre parent.
        (Bien que l'__init__ s'en charge dans le widget, cette validation est plus sûre).
        """
        cleaned_data = super().clean()
        parent = cleaned_data.get("parent")

        # Si nous sommes en modification (instance.pk existe)
        if self.instance.pk and parent and parent.pk == self.instance.pk:
            raise forms.ValidationError(
                "Une catégorie ne peut pas être sa propre catégorie parent."
            )
            
        return cleaned_data

class LivreurCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=20, required=False, label='Téléphone')
    address = forms.CharField(required=False, label='Adresse', widget=forms.Textarea(attrs={'rows': 2}))

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'phone', 'address']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = 'LIVREUR'
            profile.phone = self.cleaned_data.get('phone') or profile.phone
            profile.address = self.cleaned_data.get('address') or profile.address
            profile.save()
        return user

class DelivererUserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'is_active']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

class DelivererProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone', 'address', 'photo']
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

# Formulaires pour la page “Profil Livreur”
class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

class DelivererProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone', 'address', 'photo']
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

# Si pas encore présent
class DelivererCreateForm(UserCreationForm):
    phone = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}))
    photo = forms.ImageField(required=False, widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            UserProfile.objects.create(
                user=user,
                role=RoleChoices.LIVREUR,
                phone=self.cleaned_data.get('phone'),
                address=self.cleaned_data.get('address'),
                photo=self.cleaned_data.get('photo'),
            )
        return user

class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

class AdminProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone', 'address', 'photo']  # adapte selon tes champs UserProfile
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Téléphone'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Adresse complète'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and photo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("La photo ne peut pas dépasser 2 Mo.")
        return photo

class AdresseForm(forms.ModelForm):
    class Meta:
        model = Adresse
        fields = ['nom', 'destinataire', 'ligne1', 'ligne2', 'ville', 'region', 'code_postal', 'pays', 'telephone']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'destinataire': forms.TextInput(attrs={'class': 'form-control'}),
            'ligne1': forms.TextInput(attrs={'class': 'form-control'}),
            'ligne2': forms.TextInput(attrs={'class': 'form-control'}),
            'ville': forms.TextInput(attrs={'class': 'form-control'}),
            'region': forms.TextInput(attrs={'class': 'form-control'}),
            'code_postal': forms.TextInput(attrs={'class': 'form-control'}),
            'pays': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
        }

class StaffLivreurCreationForm(UserCreationForm):
    # Ajoutez les champs UserProfile directement dans ce formulaire
    phone = forms.CharField(max_length=15, required=False)
    address = forms.CharField(widget=forms.Textarea, required=False)
    photo = forms.ImageField(required=False)
    
    # Le champ rôle sera sélectionnable uniquement pour STAFF et LIVREUR
    # Nous utilisons un Select widget pour offrir les choix appropriés
    role = forms.ChoiceField(
        choices=[
            (RoleChoices.LIVREUR, 'Livreur'),
            (RoleChoices.STAFF, 'Staff'),
        ],
        initial=RoleChoices.STAFF # Valeur par défaut dans le formulaire
    )
    

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('first_name', 'last_name', 'email', 'phone', 'address', 'role', 'photo')

    # Cette méthode save() est cruciale pour créer les deux objets (User et UserProfile)
    def save(self, commit=True):
        user = super().save(commit=True) # Crée l'objet User standard

        # Crée l'objet UserProfile lié à l'utilisateur
        role_choice = self.cleaned_data.get('role')
        if role_choice == RoleChoices.STAFF:
             user.is_staff = True
        else:
            user.is_staff = False
        user.save()
        
        # Utilisez self.instance si vous modifiez un utilisateur existant, 
        # mais pour la création, user est l'objet que nous venons de créer.
        UserProfile.objects.create(
            user=user,
            role=role_choice,
            phone=self.cleaned_data.get('phone'),
            address=self.cleaned_data.get('address'),
            photo=self.cleaned_data.get('photo'),
            user_type=role_choice # Synchronisez user_type avec role
        )
        return user