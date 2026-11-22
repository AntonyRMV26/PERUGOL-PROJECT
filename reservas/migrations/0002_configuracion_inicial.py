from datetime import time

from django.db import migrations


def crear_configuracion(apps, schema_editor):
    alias = schema_editor.connection.alias
    grupo = apps.get_model("auth", "Group").objects.using(alias)
    for nombre in ("Administración", "Trabajadores"):
        grupo.get_or_create(name=nombre)

    cancha = apps.get_model("reservas", "Cancha").objects.using(alias)
    if not cancha.exists():
        cancha.bulk_create([cancha.model(nombre=f"Cancha {numero}") for numero in (1, 2)])

    horario = apps.get_model("reservas", "HorarioAtencion").objects.using(alias)
    horario.get_or_create(dia=0, defaults={"habilitado": False})
    for dia in range(1, 7):
        horario.get_or_create(dia=dia, defaults={"apertura": time(10), "cierre": time(23)})


class Migration(migrations.Migration):
    dependencies = [("reservas", "0001_initial")]
    operations = [migrations.RunPython(crear_configuracion, migrations.RunPython.noop)]
