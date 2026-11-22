import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from .access import tiene_acceso
from .models import Cancha, HorarioAtencion, Reserva


class AccesoForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not tiene_acceso(user):
            raise ValidationError("Tu cuenta aún no tiene acceso al sistema.", code="sin_rol")


class FechaInput(forms.DateInput):
    input_type = "date"

    def __init__(self):
        super().__init__(format="%Y-%m-%d")


class HoraInput(forms.TimeInput):
    input_type = "time"

    def __init__(self):
        super().__init__(format="%H:%M", attrs={"step": 60})


def validar_minutos(valor):
    if valor.second or valor.microsecond:
        raise ValidationError("Ingresa la hora con precisión de minutos.")


class IntervaloForm(forms.Form):
    cancha = forms.ModelChoiceField(
        queryset=Cancha.objects.filter(activa=True), empty_label="Selecciona una cancha",
    )
    fecha = forms.DateField(widget=FechaInput(), input_formats=["%Y-%m-%d"])
    inicio = forms.TimeField(label="Hora de inicio", widget=HoraInput(), validators=[validar_minutos])
    fin = forms.TimeField(label="Hora de fin", widget=HoraInput(), validators=[validar_minutos])

    def clean(self):
        datos = super().clean()
        inicio, fin = datos.get("inicio"), datos.get("fin")
        if inicio is not None and fin is not None and inicio >= fin:
            self.add_error("fin", "La hora de fin debe ser posterior a la de inicio.")
        return datos


class ReservaForm(IntervaloForm):
    cliente = forms.CharField(label="Nombre del cliente", max_length=100)
    telefono = forms.CharField(
        label="Teléfono", max_length=25,
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
    )
    canal = forms.ChoiceField(
        label="Canal de solicitud", choices=[("", "Selecciona un canal"), *Reserva.Canal.choices],
    )
    tipo_uso = forms.CharField(
        label="Tipo de uso", max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Ej. partido de fulbito"}),
    )

    def clean_telefono(self):
        valor = self.cleaned_data["telefono"]
        if not re.fullmatch(r"\+?[\d ()-]+", valor) or not 7 <= sum(c.isdecimal() for c in valor) <= 15:
            raise ValidationError("Ingresa un teléfono válido de 7 a 15 dígitos.")
        return valor


class CanchaForm(forms.ModelForm):
    class Meta:
        model = Cancha
        fields = ["nombre", "activa"]


class HorarioForm(forms.ModelForm):
    apertura = forms.TimeField(required=False, widget=HoraInput(), validators=[validar_minutos])
    cierre = forms.TimeField(required=False, widget=HoraInput(), validators=[validar_minutos])

    class Meta:
        model = HorarioAtencion
        fields = ["habilitado", "apertura", "cierre"]

    def clean(self):
        datos = super().clean()
        if not datos.get("habilitado"):
            datos.update(apertura=None, cierre=None)
            return datos
        apertura, cierre = datos.get("apertura"), datos.get("cierre")
        if apertura is None and not self.has_error("apertura"):
            self.add_error("apertura", "Indica la hora de apertura.")
        if cierre is None and not self.has_error("cierre"):
            self.add_error("cierre", "Indica la hora de cierre.")
        if apertura is not None and cierre is not None and apertura >= cierre:
            self.add_error("cierre", "El cierre debe ser posterior a la apertura.")
        return datos
