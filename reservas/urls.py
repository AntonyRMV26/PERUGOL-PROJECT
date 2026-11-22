from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import AccesoForm

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("acceso/", auth_views.LoginView.as_view(
        authentication_form=AccesoForm, template_name="reservas/acceso.html",
        redirect_authenticated_user=True,
    ), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("agenda/", views.agenda, name="agenda"),
    path("agenda/semana/", views.agenda_semanal, name="agenda_semanal"),
    path("reservas/nueva/", views.nueva_reserva, name="nueva_reserva"),
    path("reservas/disponibilidad/", views.disponibilidad, name="disponibilidad"),
    path("reservas/<int:pk>/", views.detalle, name="detalle"),
    path("configuracion/", views.configuracion, name="configuracion"),
    path("configuracion/canchas/", views.canchas, name="canchas"),
]
