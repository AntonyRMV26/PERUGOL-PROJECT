from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

ADMINISTRACION = "Administración"
TRABAJADORES = "Trabajadores"


def es_administrador(usuario):
    return usuario.is_superuser or usuario.groups.filter(name=ADMINISTRACION).exists()


def tiene_acceso(usuario):
    return usuario.is_superuser or usuario.groups.filter(name__in=[ADMINISTRACION, TRABAJADORES]).exists()


def acceso_requerido(view=None, *, administrador=False):
    def decorate(func):
        @login_required
        @wraps(func)
        def wrapped(request, *args, **kwargs):
            request.es_administrador = es_administrador(request.user)
            if not request.es_administrador and (administrador or not tiene_acceso(request.user)):
                raise PermissionDenied
            return func(request, *args, **kwargs)

        return wrapped

    return decorate(view) if view is not None else decorate
