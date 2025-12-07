from django.urls import path
from . import views

urlpatterns = [
    # tes routes ici
    path('', views.index, name='index'),
]
