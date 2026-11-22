from datetime import time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from reservas.access import ADMINISTRACION, TRABAJADORES
from reservas.models import Cancha, Reserva
from reservas.servicios import ReservaInvalida, registrar_reserva


class Command(BaseCommand):
    help = "Crea dos cuentas locales de demostración. Opcionalmente agrega reservas ficticias."

    def add_arguments(self, parser):
        parser.add_argument("--ejemplos", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or settings.DATABASES["default"]["HOST"] not in ("localhost", "127.0.0.1", "::1"):
            raise CommandError("Las cuentas de demostración requieren una base local y DJANGO_DEBUG=1.")

        user_model = get_user_model()
        usuarios = (
            ("administradora_demo", "GolDemo-Admin26!", ADMINISTRACION),
            ("trabajador_demo", "GolDemo-Trabajo26!", TRABAJADORES),
        )
        trabajador = None
        for nombre, clave, rol in usuarios:
            usuario, creado = user_model.objects.get_or_create(username=nombre)
            if creado:
                usuario.set_password(clave)
                usuario.save(update_fields=["password"])
                usuario.groups.add(Group.objects.get(name=rol))
                self.stdout.write(f"{nombre} / {clave}")
            else:
                self.stdout.write(f"{nombre} ya existe.")
            if rol == TRABAJADORES and usuario.groups.filter(name=rol).exists():
                trabajador = usuario

        if options["ejemplos"] and trabajador:
            fecha = timezone.localdate()
            if fecha.weekday() == 0:
                fecha += timedelta(days=1)
            for cancha, horas in zip(Cancha.objects.filter(activa=True)[:2], [(11, 17), (12, 18)]):
                for hora in horas:
                    try:
                        registrar_reserva({
                            "cancha": cancha, "fecha": fecha, "inicio": time(hora), "fin": time(hora + 1),
                            "cliente": "Cliente de demostración", "telefono": "900000000",
                            "tipo_uso": "Partido de fulbito", "canal": Reserva.Canal.WHATSAPP,
                        }, trabajador)
                    except ReservaInvalida:
                        continue
            self.stdout.write(f"Agenda de ejemplo preparada para {fecha:%d/%m/%Y}.")
