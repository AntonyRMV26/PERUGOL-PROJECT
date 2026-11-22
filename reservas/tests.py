from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Barrier

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from .access import ADMINISTRACION, TRABAJADORES
from .models import CambioConfiguracion, Cancha, HorarioAtencion, Reserva

MARTES = date(2026, 11, 24)
CLAVE = "Prueba-PeruGol-2026!"


def crear_usuario(nombre, rol=None):
    usuario = get_user_model().objects.create_user(nombre, password=CLAVE)
    if rol:
        usuario.groups.add(Group.objects.get(name=rol))
    return usuario


def datos_reserva(cancha, /, **cambios):
    return {
        "cancha": cancha.pk, "fecha": MARTES.isoformat(), "inicio": "18:00", "fin": "19:00",
        "cliente": "Cliente de prueba", "telefono": "987654321", "tipo_uso": "Fulbito", "canal": "llamada",
    } | cambios


class SprintUnoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.trabajador = crear_usuario("empleado", TRABAJADORES)
        cls.administradora = crear_usuario("administradora", ADMINISTRACION)
        cls.sin_rol = crear_usuario("sin_rol")
        cls.cancha, cls.otra_cancha = Cancha.objects.all()

    def reservar(self, **cambios):
        return self.client.post(reverse("nueva_reserva"), datos_reserva(self.cancha, **cambios))

    def test_ingreso_y_control_de_roles(self):
        configuracion = reverse("configuracion")
        self.assertRedirects(self.client.get(configuracion), reverse("login") + "?next=" + configuracion)
        respuesta = self.client.post(reverse("login"), {"username": self.sin_rol.username, "password": CLAVE})
        self.assertContains(respuesta, "Tu cuenta aún no tiene acceso")
        self.assertRedirects(self.client.post(reverse("login"), {
            "username": self.trabajador.username, "password": CLAVE,
        }), reverse("inicio"))
        self.assertEqual(self.client.get(configuracion).status_code, 403)
        self.assertEqual(self.client.post(reverse("canchas")).status_code, 403)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))
        self.client.force_login(self.administradora)
        self.assertContains(self.client.get(configuracion), "Horarios de atención")

    def test_reserva_agenda_autoria_y_superposicion(self):
        self.client.force_login(self.trabajador)
        reserva = self.reservar(cliente="Reserva guardada")
        self.assertEqual(reserva.status_code, 302)
        guardada = Reserva.objects.get()
        self.assertEqual(guardada.registrado_por, self.trabajador)
        self.assertIsNotNone(guardada.registrado_en)

        cruce = self.reservar(inicio="18:30", fin="19:30")
        self.assertContains(cruce, "La cancha ya está ocupada")
        self.assertContains(cruce, "Horarios alternativos")
        self.assertEqual(Reserva.objects.count(), 1)
        self.assertEqual(self.reservar(inicio="19:00", fin="20:00").status_code, 302)
        self.assertEqual(self.reservar(cancha=self.otra_cancha.pk).status_code, 302)
        self.assertEqual(self.reservar(fecha="2026-11-25").status_code, 302)

        parametros = {"fecha": MARTES.isoformat(), "cancha": self.cancha.pk}
        for vista in ("agenda", "agenda_semanal"):
            self.assertContains(self.client.get(reverse(vista), parametros), "Reserva guardada")
        self.assertContains(self.client.get(reserva.url), self.trabajador.username)
        self.assertContains(
            self.client.get(reverse("nueva_reserva"), parametros | {"inicio": "16:00", "fin": "17:00"}),
            'value="16:00"',
        )

    def test_rechaza_dia_cerrado_orden_y_rango_de_horas(self):
        self.client.force_login(self.trabajador)
        self.assertContains(self.reservar(fecha="2026-11-23"), "Ese día está cerrado")
        self.assertContains(self.reservar(inicio="22:30", fin="23:30"), "entre las 10:00 y las 23:00")
        self.assertContains(self.reservar(inicio="20:00", fin="19:00"), "posterior a la de inicio")
        self.assertContains(self.reservar(inicio="19:00:30"), "precisión de minutos")
        self.assertFalse(Reserva.objects.exists())
        disponible = self.client.get(reverse("disponibilidad"), datos_reserva(self.cancha))
        self.assertTrue(disponible.json()["disponible"])

    def test_configuracion_actualiza_validacion_y_conserva_reservas(self):
        self.client.force_login(self.administradora)
        self.assertEqual(self.reservar().status_code, 302)
        datos = {
            f"dia-{dia}-{campo}": valor
            for dia in range(1, 7)
            for campo, valor in {"habilitado": "on", "apertura": "10:00", "cierre": "23:00"}.items()
        }
        datos["dia-1-cierre"] = "18:00"
        self.assertRedirects(self.client.post(reverse("configuracion"), datos), reverse("configuracion"))
        self.assertEqual(HorarioAtencion.objects.get(dia=1).cierre, time(18))
        self.assertEqual(CambioConfiguracion.objects.get().usuario, self.administradora)
        self.assertContains(self.reservar(inicio="19:00", fin="20:00"), "entre las 10:00 y las 18:00")
        self.assertEqual(Reserva.objects.count(), 1)
        self.assertContains(self.client.get(reverse("agenda"), {"fecha": MARTES}), "Cliente de prueba")

        prefijo = f"cancha-{self.otra_cancha.pk}"
        self.client.post(reverse("canchas"), {
            "cancha": self.otra_cancha.pk, f"{prefijo}-nombre": "Cancha Norte",
        })
        self.otra_cancha.refresh_from_db()
        self.assertFalse(self.otra_cancha.activa)
        self.assertEqual(self.otra_cancha.nombre, "Cancha Norte")
        self.assertContains(self.reservar(cancha=self.otra_cancha.pk), "opción válida")

        respuesta = self.client.post(reverse("canchas"), {"cancha-nueva-nombre": "Cancha Sur", "cancha-nueva-activa": "on"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Cancha.objects.filter(nombre="Cancha Sur", activa=True).exists())

    def test_restriccion_postgres_sin_pasarla_por_la_vista(self):
        datos = {
            "cancha": self.cancha, "fecha": MARTES, "cliente": "Prueba",
            "telefono": "900000000", "registrado_por": self.trabajador, "tipo_uso": "Fulbito", "canal": "llamada",
        }
        Reserva.objects.create(**datos, inicio=time(18), fin=time(19))
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            Reserva.objects.create(**datos, inicio=time(18, 30), fin=time(19, 30))
        self.assertEqual(error.exception.__cause__.diag.constraint_name, "reserva_sin_solapamiento")
        Reserva.objects.create(**datos, inicio=time(19), fin=time(20))


class ConcurrenciaTests(TransactionTestCase):
    def test_dos_solicitudes_simultaneas_guardan_maximo_una(self):
        cancha = Cancha.objects.get(nombre="Cancha 1")
        usuarios = [crear_usuario(nombre, TRABAJADORES) for nombre in ("operador_a", "operador_b")]
        inicio_simultaneo = Barrier(2)

        def intentar(usuario):
            try:
                cliente = Client()
                cliente.force_login(usuario)
                inicio_simultaneo.wait(timeout=10)
                return cliente.post(reverse("nueva_reserva"), datos_reserva(cancha)).status_code
            finally:
                connections.close_all()

        self.assertEqual(connection.vendor, "postgresql")
        with ThreadPoolExecutor(max_workers=2) as executor:
            estados = sorted(executor.map(intentar, usuarios))
        self.assertEqual(estados, [200, 302])
        self.assertEqual(Reserva.objects.count(), 1)
