from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import acceso_requerido
from .agenda import Columna, duracion_disponible, filas_agenda
from .forms import CanchaForm, HorarioForm, IntervaloForm, ReservaForm
from .models import DIAS, CambioConfiguracion, Cancha, HorarioAtencion, Reserva
from .servicios import ReservaInvalida, bloques_agenda, comprobar_disponibilidad, registrar_reserva


def fecha_elegida(request):
    try:
        return date.fromisoformat(request.GET.get("fecha", ""))
    except ValueError:
        return timezone.localdate()


def mover_fecha(fecha, dias):
    return date.fromordinal(min(max(fecha.toordinal() + dias, 1), date.max.toordinal()))


def url_con_parametros(nombre, **parametros):
    return f"{reverse(nombre)}?{urlencode(parametros)}"


def elegir_cancha(canchas, valor):
    return next((c for c in canchas if str(c.pk) == valor), next(iter(canchas), None))


def abreviatura(dia):
    return DIAS[dia][1][:3]


@acceso_requerido
@require_GET
def inicio(request):
    hoy = timezone.localdate()
    hora_actual = timezone.localtime().time()
    canchas = list(Cancha.objects.filter(activa=True))
    horario = HorarioAtencion.objects.filter(dia=hoy.weekday()).first()
    reservas_hoy = list(Reserva.objects.filter(fecha=hoy).select_related("cancha"))
    minutos = sum(
        duracion_disponible(bloques_agenda(horario, [r for r in reservas_hoy if r.cancha_id == cancha.id]))
        for cancha in canchas
    )
    proximas = Reserva.objects.filter(fecha__gt=hoy) | Reserva.objects.filter(fecha=hoy, fin__gt=hora_actual)
    horas, resto = divmod(minutos, 60)
    return render(request, "reservas/inicio.html", {
        "hoy": hoy, "horario": horario, "cantidad_canchas": len(canchas),
        "cantidad_reservas": len(reservas_hoy), "horas_libres": f"{horas} h {resto:02d} min",
        "proximas": proximas.select_related("cancha")[:6],
    })


@acceso_requerido
@require_GET
def agenda(request):
    fecha = fecha_elegida(request)
    reservas = defaultdict(list)
    for reserva in Reserva.objects.filter(fecha=fecha):
        reservas[reserva.cancha_id].append(reserva)
    horario = HorarioAtencion.objects.filter(dia=fecha.weekday()).first()
    canchas = list(Cancha.objects.filter(activa=True) | Cancha.objects.filter(id__in=reservas.keys()))
    cancha = elegir_cancha(canchas, request.GET.get("cancha"))
    columnas = []
    for c in canchas:
        columnas.append(Columna(
            c.nombre, bloques_agenda(horario, reservas[c.id], activa=c.activa),
            url_con_parametros("nueva_reserva", fecha=fecha, cancha=c.pk),
        ))
    parametros = {"cancha": cancha.pk} if cancha else {}
    return render(request, "reservas/agenda.html", {
        "fecha": fecha, "hoy": timezone.localdate(), "horario": horario,
        "canchas": canchas, "cancha": cancha, "columnas": columnas, "filas": filas_agenda(columnas),
        "columna_movil": columnas[canchas.index(cancha)] if cancha else None,
        "modo": "diaria", "ruta": "agenda",
        "anterior": url_con_parametros("agenda", fecha=mover_fecha(fecha, -1), **parametros),
        "siguiente": url_con_parametros("agenda", fecha=mover_fecha(fecha, 1), **parametros),
        "actual": url_con_parametros("agenda", fecha=timezone.localdate(), **parametros),
    })


@acceso_requerido
@require_GET
def agenda_semanal(request):
    fecha = fecha_elegida(request)
    lunes = fecha - timedelta(days=fecha.weekday())
    dias = [mover_fecha(lunes, i) for i in range(min(7, (date.max - lunes).days + 1))]
    domingo = dias[-1]
    reservas_semana = Reserva.objects.filter(fecha__range=(lunes, domingo))
    canchas = list(
        (Cancha.objects.filter(activa=True) | Cancha.objects.filter(id__in=reservas_semana.values("cancha_id")))
    )
    cancha = elegir_cancha(canchas, request.GET.get("cancha"))
    reservas = defaultdict(list)
    for reserva in reservas_semana.filter(cancha=cancha) if cancha else []:
        reservas[reserva.fecha].append(reserva)
    horarios = {h.dia: h for h in HorarioAtencion.objects.all()}
    parametros = {"cancha": cancha.pk} if cancha else {}
    columnas, dias_movil = [], []
    for dia in dias:
        columnas.append(Columna(
            abreviatura(dia.weekday()) + dia.strftime(" %d/%m"),
            bloques_agenda(horarios.get(dia.weekday()), reservas[dia], activa=bool(cancha and cancha.activa)),
            url_con_parametros("nueva_reserva", fecha=dia, **parametros),
        ))
        dias_movil.append({
            "titulo": abreviatura(dia.weekday()), "fecha": dia,
            "url": url_con_parametros("agenda_semanal", fecha=dia, **parametros),
        })
    return render(request, "reservas/agenda.html", {
        "fecha": fecha, "hoy": timezone.localdate(), "modo": "semanal", "ruta": "agenda_semanal",
        "lun": lunes, "dom": domingo, "canchas": canchas, "cancha": cancha,
        "columnas": columnas, "filas": filas_agenda(columnas),
        "dias_movil": dias_movil, "columna_movil": columnas[dias.index(fecha)] if cancha else None,
        "anterior": url_con_parametros("agenda_semanal", fecha=mover_fecha(fecha, -7), **parametros),
        "siguiente": url_con_parametros("agenda_semanal", fecha=mover_fecha(fecha, 7), **parametros),
        "actual": url_con_parametros("agenda_semanal", fecha=timezone.localdate(), **parametros),
    })


@acceso_requerido
@require_http_methods(["GET", "POST"])
def nueva_reserva(request):
    alternativas = ()
    inicial = {"fecha": fecha_elegida(request)}
    if request.method == "GET":
        # Normaliza los datos de la URL sin confiar en ellos al guardar.
        cancha = next((c for c in Cancha.objects.filter(activa=True) if str(c.pk) == request.GET.get("cancha")), None)
        inicial["cancha"] = cancha
        for campo in ("inicio", "fin"):
            try:
                inicial[campo] = IntervaloForm.base_fields[campo].clean(request.GET.get(campo))
            except ValidationError:
                pass
    form = ReservaForm(request.POST if request.method == "POST" else None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        try:
            reserva = registrar_reserva(form.cleaned_data, request.user)
        except ReservaInvalida as error:
            form.add_error(None, str(error))
            alternativas = error.alternativas
        else:
            messages.success(request, "Reserva registrada. La agenda se actualizó.")
            return redirect("detalle", pk=reserva.pk)
    return render(request, "reservas/nueva.html", {"form": form, "alternativas": alternativas})


@acceso_requerido
@require_GET
def disponibilidad(request):
    form = IntervaloForm(request.GET)
    if not form.is_valid():
        mensaje = next(iter(form.errors.values()))[0]
        return JsonResponse({"disponible": False, "mensaje": mensaje}, status=400)
    try:
        comprobar_disponibilidad(**form.cleaned_data)
    except ReservaInvalida as error:
        return JsonResponse({
            "disponible": False, "mensaje": str(error),
            "alternativas": [[inicio.strftime("%H:%M"), fin.strftime("%H:%M")] for inicio, fin in error.alternativas],
        })
    return JsonResponse({"disponible": True, "mensaje": "Horario disponible. Se comprobará de nuevo al guardar."})


@acceso_requerido
@require_GET
def detalle(request, pk):
    reserva = get_object_or_404(Reserva.objects.select_related("cancha", "registrado_por"), pk=pk)
    return render(request, "reservas/detalle.html", {
        "reserva": reserva,
        "agenda_url": url_con_parametros("agenda", fecha=reserva.fecha, cancha=reserva.cancha_id),
    })


def resumen_horario(horario):
    return f"{horario.apertura:%H:%M}–{horario.cierre:%H:%M}" if horario.habilitado else "Cerrado"


def resumen_cancha(cancha):
    return f"{cancha.nombre} · {'Habilitada' if cancha.activa else 'Deshabilitada'}"


def configuracion_contexto(horarios=None, formulario_cancha=None):
    if horarios is None:
        horarios = [
            (h.get_dia_display(), HorarioForm(instance=h, prefix=f"dia-{h.dia}"))
            for h in HorarioAtencion.objects.all()
        ]
    canchas = list(Cancha.objects.all())
    return {
        "horarios": horarios,
        "canchas": [
            (c, formulario_cancha if formulario_cancha and formulario_cancha.instance.pk == c.pk
             else CanchaForm(instance=c, prefix=f"cancha-{c.pk}"))
            for c in canchas
        ],
        "nueva_cancha": formulario_cancha if formulario_cancha and not formulario_cancha.instance.pk
        else CanchaForm(prefix="cancha-nueva"),
        "cambios": CambioConfiguracion.objects.select_related("usuario")[:10],
    }


@acceso_requerido(administrador=True)
@require_http_methods(["GET", "POST"])
def configuracion(request):
    if request.method == "GET":
        return render(request, "reservas/configuracion.html", configuracion_contexto())

    with transaction.atomic():
        horarios = list(HorarioAtencion.objects.select_for_update())
        anteriores = {h.dia: resumen_horario(h) for h in horarios}
        formularios = [
            (h.get_dia_display(), HorarioForm(request.POST, instance=h, prefix=f"dia-{h.dia}"))
            for h in horarios
        ]
        if all([form.is_valid() for _, form in formularios]):
            for dia, form in formularios:
                actual = resumen_horario(form.instance)
                anterior = anteriores[form.instance.dia]
                if actual != anterior:
                    form.save()
                    CambioConfiguracion.objects.create(
                        usuario=request.user, elemento=dia, anterior=anterior, actual=actual,
                    )
            messages.success(request, "Horarios guardados.")
            return redirect("configuracion")
    return render(request, "reservas/configuracion.html", configuracion_contexto(horarios=formularios))


@acceso_requerido(administrador=True)
@require_POST
def canchas(request):
    identificador = request.POST.get("cancha")
    if identificador and (not identificador.isascii() or not identificador.isdecimal() or len(identificador) > 18):
        raise Http404
    try:
        with transaction.atomic():
            cancha = get_object_or_404(Cancha.objects.select_for_update(), pk=identificador) if identificador else None
            anterior = resumen_cancha(cancha) if cancha else ""
            form = CanchaForm(request.POST, instance=cancha, prefix=f"cancha-{cancha.pk if cancha else 'nueva'}")
            if form.is_valid():
                actual = resumen_cancha(form.instance)
                if anterior != actual:
                    form.save()
                    CambioConfiguracion.objects.create(
                        usuario=request.user, elemento=f"Cancha #{form.instance.pk}", anterior=anterior, actual=actual,
                    )
                messages.success(request, "Cancha guardada.")
                return redirect(reverse("configuracion") + "#canchas")
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) != "cancha_nombre_unico":
            raise
        form.instance.pk = cancha.pk if cancha else None
        form.add_error("nombre", "Ya existe una cancha con ese nombre.")
    return render(request, "reservas/configuracion.html", configuracion_contexto(formulario_cancha=form))
