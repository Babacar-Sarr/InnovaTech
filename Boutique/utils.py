# Dans un fichier comme votre_app/utils.py

from django.core.mail import send_mail
from django.conf import settings

def envoyer_mail_statut_commande(commande, statut_precedent=None):
    """
    Envoie un email au client concernant le statut de sa commande.
    """
    # Assurez-vous que l'utilisateur a un email pour l'envoi
    if not commande.user.email:
        print(f"Erreur: L'utilisateur {commande.user.username} n'a pas d'email.")
        return

    # 1. Définition du contenu spécifique au statut
    if commande.statut == 'EN_COURS':
        sujet = f"Mise à jour : Votre commande #{commande.id} est en cours de livraison !"
        message_statut = f"""
**Votre commande est en cours !**
Vous serez contacté pour la livraison qui se fera dans les **prochains 2 jours**.
Le livreur est en route. Vous pouvez suivre sa position en temps réel (si l'interface le permet).
"""
    elif commande.statut == 'LIVREE':
        sujet = f"Commande #{commande.id} livrée avec succès"
        message_statut = "Votre commande a été **livrée** ! Nous espérons que tout vous plaît."
    elif commande.statut == 'ANNULEE':
        sujet = f"Annulation de votre commande #{commande.id}"
        message_statut = "Votre commande a été **annulée** à votre demande ou par nos services."
    elif statut_precedent is None or commande.statut == 'EN_ATTENTE':
        # C'est probablement la première fois que la commande est enregistrée
        sujet = f"Confirmation de votre commande #{commande.id}"
        message_statut = "Nous vous remercions pour votre achat. Votre commande est actuellement en **attente** de traitement."
    else:
        # Aucun changement ou statut non géré
        return

    # 2. Construction du message complet
    message_base = f"""
Bonjour {commande.user.username},

{message_statut}

---
Détails de votre commande :
Numéro de commande : #{commande.id}
Statut actuel : {commande.get_statut_display()}
Date de commande : {commande.date_commande.strftime('%d/%m/%Y à %H:%M')}
Montant total : {commande.total} F CFA

Articles :
"""
    # Ajout de la liste des articles
    items_list = ""
    for item in commande.items.all():
        # Assurez-vous que votre modèle Produit a bien un champ 'nom'
        items_list += f"- {item.quantite}x {item.produit.nom} ({item.prix_unitaire} F CFA / unité)\n"
        
    message_final = f"""{message_base}{items_list}
---
Merci de votre confiance.
L'équipe de [Votre Boutique/Site].
"""

    # 3. Envoi de l'email
    try:
        send_mail(
            sujet,
            message_final,
            settings.EMAIL_HOST_USER,
            [commande.user.email], # Destinataire
            fail_silently=False,
        )
        print(f"Email de statut envoyé pour la commande #{commande.id} à {commande.user.email}")
    except Exception as e:
        # Gérer les erreurs d'envoi (ex: mauvaise configuration SMTP)
        print(f"Erreur lors de l'envoi de l'email pour la commande #{commande.id} : {e}")