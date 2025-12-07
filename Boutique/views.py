from django.shortcuts import render, redirect, get_object_or_404
# Create your views here.
def index(request):
    """Page d'accueil - redirige vers la boutique"""
    return render(request, "base.html")