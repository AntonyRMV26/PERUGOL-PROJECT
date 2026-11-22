from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import F, Func, Q, Value
from django.db.models.functions import Lower

DIAS = (
    (0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"),
    (4, "Viernes"), (5, "Sábado"), (6, "Domingo"),
)


class Cancha(models.Model):
    nombre = models.CharField("nombre", max_length=60)
    activa = models.BooleanField("habilitada", default=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(Lower("nombre"), name="cancha_nombre_unico"),
        ]

    def __str__(self):
        return self.nombre


class HorarioAtencion(models.Model):
    dia = models.PositiveSmallIntegerField(choices=DIAS, unique=True)
    habilitado = models.BooleanField(default=True)
    apertura = models.TimeField(null=True, blank=True)
    cierre = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["dia"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(habilitado=False, apertura__isnull=True, cierre__isnull=True)
                    | Q(habilitado=True, apertura__isnull=False, cierre__isnull=False, apertura__lt=F("cierre"))
                ),
                name="horario_atencion_valido",
            ),
        ]


class Reserva(models.Model):
    class Canal(models.TextChoices):
        PRESENCIAL = "presencial", "Presencial"
        LLAMADA = "llamada", "Llamada"
        WHATSAPP = "whatsapp", "WhatsApp"

    cancha = models.ForeignKey(Cancha, on_delete=models.PROTECT, related_name="reservas")
    fecha = models.DateField()
    inicio = models.TimeField()
    fin = models.TimeField()
    cliente = models.CharField(max_length=100)
    telefono = models.CharField(max_length=25)
    tipo_uso = models.CharField(max_length=100)
    canal = models.CharField(max_length=12, choices=Canal.choices)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha", "inicio", "id"]
        indexes = [models.Index(fields=["fecha", "cancha", "inicio"])]
        constraints = [
            models.CheckConstraint(condition=Q(inicio__lt=F("fin")), name="reserva_horas_validas"),
            ExclusionConstraint(
                name="reserva_sin_solapamiento",
                expressions=[
                    ("cancha", RangeOperators.EQUAL),
                    (
                        Func(
                            F("fecha") + F("inicio"), F("fecha") + F("fin"), Value("[)"),
                            function="TSRANGE", output_field=DateTimeRangeField(),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
            ),
        ]


class CambioConfiguracion(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    elemento = models.CharField(max_length=60)
    anterior = models.CharField(max_length=100, blank=True)
    actual = models.CharField(max_length=100)

    class Meta:
        ordering = ["-fecha", "-id"]
