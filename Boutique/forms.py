from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import Produit, Categorie, UserProfile, RoleChoices, Adresse

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

class CategorieForm(forms.ModelForm):
    class Meta:
        model = Categorie
        fields = ['nom', 'description', 'icon']
        labels = {
            'nom': 'Nom',
            'description': 'Description',
            'icon': 'Icône (classe FontAwesome)',
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'icon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ex: fa-solid fa-tag'}),
        }

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