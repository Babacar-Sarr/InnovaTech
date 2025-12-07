"""
Constantes partagées dans l'application
"""
from decimal import Decimal

# Frais de livraison par défaut (en FCFA)
FRAIS_LIVRAISON_DEFAUT = Decimal('1000')

# Autres constantes
STATUTS_COMMANDE = [
    ('EN_ATTENTE', 'En attente'),
    ('EN_COURS', 'En cours'),
    ('LIVREE', 'Livrée'),
    ('ANNULEE', 'Annulée'),
]