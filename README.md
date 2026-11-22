# Perú Gol

MVP del Sprint 1 para gestionar las reservas de las canchas de Gol Perú. Es un sistema interno para administración y trabajadores.

| Historia | Funcionalidad |
| --- | --- |
| HU01 · RF07 | Inicio y cierre de sesión, permisos por rol y autoría de las reservas y cambios de configuración. |
| HU02 · RF08 | Alta y edición de canchas, habilitación por cancha y horarios de atención. Inicialmente hay dos canchas y se atiende de martes a domingo de 10:00 a 23:00. |
| HU03 · RF01 | Alta de reservas con cliente, teléfono, cancha, fecha, horas, tipo de uso y canal. |
| HU04 · RF02 | Agendas diaria y semanal, consulta de disponibilidad, aviso de cruce y sugerencias de horarios alternativos. |

## Probar en local

Necesitas Python 3.12 o superior y PostgreSQL. Con Docker Compose, levanta la base desde la raíz del repositorio.

```powershell
docker compose up -d --wait
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py demo --ejemplos
.\.venv\Scripts\python.exe manage.py runserver
```

Abre [http://127.0.0.1:8000](http://127.0.0.1:8000). El comando `demo` crea estas cuentas para pruebas locales y `--ejemplos` agrega reservas ficticias.

| Rol | Usuario | Contraseña |
| --- | --- | --- |
| Administración | `administradora_demo` | `GolDemo-Admin26!` |
| Trabajador | `trabajador_demo` | `GolDemo-Trabajo26!` |

En macOS o Linux, usa `python3 -m venv .venv` y `.venv/bin/python` en los comandos. Si ya tienes PostgreSQL, crea una base y ajusta las variables `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGHOST` y `PGPORT` antes de migrar. La migración inicial requiere la extensión `btree_gist`. La conexión local predeterminada coincide con `compose.yaml` y usa el puerto `55432`.

### Recorrido para la demo

1. Entra como trabajador. Abre la agenda diaria, selecciona un horario libre y registra una reserva. El detalle muestra quién la creó y cuándo.
2. En la misma cancha, prueba guardar un intervalo que se cruce y otro que empiece exactamente al terminar la primera reserva. Comprueba ambas agendas y revisa la vista semanal en un ancho de celular.
3. Entra como administradora. Cambia un horario o deshabilita una cancha y verifica que el formulario aplique la nueva configuración. Las reservas ya guardadas se conservan y los cambios quedan registrados.

La disponibilidad se consulta desde el formulario y se revalida en el servidor al guardar. PostgreSQL aplica una restricción de exclusión para impedir cruces en la misma cancha y permitir reservas contiguas. La confirmación al cliente por WhatsApp es manual.

Para crear cuentas propias, ejecuta `manage.py createsuperuser` con el Python del entorno virtual. Desde `/admin/`, crea los usuarios y asígnalos al grupo **Administración** o **Trabajadores**. El panel técnico de Django se usa para gestionar cuentas.

## Pruebas y respaldo

```powershell
.\.venv\Scripts\python.exe manage.py test
```

El usuario de desarrollo debe poder crear una base temporal para las pruebas. La suite comprueba los permisos, la autoría, el horario de atención, los límites entre reservas y dos solicitudes simultáneas.

Para respaldar la base local con Compose:

```powershell
New-Item -ItemType Directory -Force backups
docker compose exec -T postgres pg_dump -U perugol -d perugol -Fc -f /tmp/perugol.dump
docker compose cp postgres:/tmp/perugol.dump backups/perugol.dump
```

Con un cliente PostgreSQL local, puedes usar `pg_dump -Fc -h 127.0.0.1 -p 55432 -U perugol -f backups/perugol.dump perugol`. El archivo incluye datos de clientes. Guárdalo fuera de Git.

Las tarifas, los pagos y las deudas corresponden al Sprint 2. El cierre diario, la reprogramación, la cancelación y las ausencias corresponden al alcance planteado para el Sprint 3. La revisión de otro integrante y la demo con la administradora quedan pendientes según la Definición de Terminado propuesta.
