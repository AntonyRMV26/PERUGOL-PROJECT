from dataclasses import dataclass
from datetime import time

from django.db import IntegrityError, transaction

from .models import Cancha, HorarioAtencion, Reserva


@dataclass(frozen=True)
class Bloque:
    inicio: time
    fin: time
    estado: str
    reserva: Reserva | None = None


class ReservaInvalida(Exception):
    def __init__(self, mensaje, alternativas=()):
        super().__init__(mensaje)
        self.alternativas = alternativas


def minutos(hora):
    return hora.hour * 60 + hora.minute


def hora_de(minuto):
    return time(*divmod(minuto, 60))


def bloques_agenda(horario, reservas, *, activa=True):
    reservas = list(reservas)
    abierto = activa and horario is not None and horario.habilitado
    limites = {hora for r in reservas for hora in (r.inicio, r.fin)}
    if abierto:
        limites.update((horario.apertura, horario.cierre))
    limites = sorted(limites)

    bloques = []
    pendientes = iter(reservas)
    reserva = next(pendientes, None)
    for inicio, fin in zip(limites, limites[1:]):
        if reserva and inicio >= reserva.fin:
            reserva = next(pendientes, None)
        if reserva and reserva.inicio <= inicio < reserva.fin:
            if bloques and bloques[-1].reserva == reserva:
                bloques.pop()
            bloques.append(Bloque(reserva.inicio, fin, "ocupado", reserva))
        elif abierto and horario.apertura <= inicio and fin <= horario.cierre:
            for minuto in range(minutos(inicio), minutos(fin), 60):
                bloques.append(Bloque(hora_de(minuto), hora_de(min(minuto + 60, minutos(fin))), "libre"))
        else:
            bloques.append(Bloque(inicio, fin, "cerrado"))
    return bloques


def horarios_alternativos(horario, reservas, inicio, fin):
    duracion = minutos(fin) - minutos(inicio)
    cortes = [horario.apertura]
    resultados = []
    for reserva in reservas:
        if reserva.fin <= horario.apertura or reserva.inicio >= horario.cierre:
            continue
        cortes.extend([max(reserva.inicio, horario.apertura), min(reserva.fin, horario.cierre)])
    cortes.append(horario.cierre)
    for desde, hasta in zip(cortes[::2], cortes[1::2]):
        if minutos(hasta) - minutos(desde) >= duracion:
            candidato = min(max(minutos(inicio), minutos(desde)), minutos(hasta) - duracion)
            resultados.append((hora_de(candidato), hora_de(candidato + duracion)))
    return sorted(resultados, key=lambda rango: abs(minutos(rango[0]) - minutos(inicio)))[:3]


def comprobar_disponibilidad(cancha, fecha, inicio, fin, *, horario=None):
    if not cancha.activa:
        raise ReservaInvalida("Esta cancha está deshabilitada. Elige otra cancha.")
    if horario is None:
        horario = HorarioAtencion.objects.filter(dia=fecha.weekday()).first()
    if not horario or not horario.habilitado:
        raise ReservaInvalida("Ese día está cerrado. Elige otra fecha.")
    if not horario.apertura <= inicio < fin <= horario.cierre:
        raise ReservaInvalida(
            f"El intervalo debe estar entre las {horario.apertura:%H:%M} y las {horario.cierre:%H:%M}."
        )
    reservas = Reserva.objects.filter(cancha=cancha, fecha=fecha)
    if reservas.filter(inicio__lt=fin, fin__gt=inicio).exists():
        raise ReservaInvalida(
            "La cancha ya está ocupada en parte o en todo ese horario.",
            horarios_alternativos(horario, reservas, inicio, fin),
        )


def registrar_reserva(datos, usuario):
    intervalo = {campo: datos[campo] for campo in ("cancha", "fecha", "inicio", "fin")}
    try:
        with transaction.atomic():
            # El día y la cancha se bloquean en el mismo orden al registrar.
            # Sus modificaciones de configuración usan los mismos bloqueos.
            horario = HorarioAtencion.objects.select_for_update().get(dia=datos["fecha"].weekday())
            cancha = Cancha.objects.select_for_update().get(pk=datos["cancha"].pk)
            intervalo["cancha"] = cancha
            comprobar_disponibilidad(**intervalo, horario=horario)
            return Reserva.objects.create(**(datos | intervalo), registrado_por=usuario)
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) != "reserva_sin_solapamiento":
            raise
        comprobar_disponibilidad(**intervalo)
        raise ReservaInvalida("Ese horario acaba de ocuparse. Consulta la agenda y elige otro.") from error
