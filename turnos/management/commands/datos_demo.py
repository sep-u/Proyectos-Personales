"""Carga (o borra) datos de demostración para probar el dashboard de staff.

    python manage.py datos_demo            # carga 90 días de reservas pasadas
    python manage.py datos_demo --dias 30  # otro rango
    python manage.py datos_demo --borrar   # elimina solo los datos demo

Solo crea reservas en fechas pasadas, para no ocupar horarios futuros que
pueden reservar clientes reales. Todo lo demo se identifica por usuarios
cuyo username empieza con "demo_".
"""
import random
from datetime import time, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from turnos.models import EstadoReserva, HorarioDisponible, PrecioServicio, Reserva

PREFIJO = "demo_"
HORAS = [time(h) for h in (9, 10, 11, 12, 14, 15, 16, 17)]
NOMBRES = [
    ("Camila", "Rojas"), ("Matías", "González"), ("Valentina", "Muñoz"), ("Benjamín", "Díaz"),
    ("Sofía", "Pérez"), ("Joaquín", "Soto"), ("Isidora", "Contreras"), ("Vicente", "Silva"),
    ("Florencia", "Martínez"), ("Tomás", "Sepúlveda"), ("Antonia", "Morales"), ("Agustín", "Rodríguez"),
    ("Martina", "López"), ("Maximiliano", "Fuentes"), ("Catalina", "Hernández"), ("Lucas", "Torres"),
    ("Javiera", "Araya"), ("Diego", "Flores"), ("Fernanda", "Espinoza"), ("Cristóbal", "Valenzuela"),
    ("Constanza", "Castillo"), ("Nicolás", "Reyes"), ("Emilia", "Gutiérrez"), ("Sebastián", "Vargas"),
    ("Trinidad", "Castro"), ("Felipe", "Álvarez"), ("Josefa", "Tapia"), ("Ignacio", "Carrasco"),
]
AUTOS = [
    "Toyota Yaris", "Chevrolet Sail", "Suzuki Swift", "Kia Rio", "Hyundai Accent", "Nissan Versa",
    "Mazda 3", "Toyota RAV4", "Kia Sportage", "Hyundai Tucson", "Chevrolet Tracker", "Nissan X-Trail",
    "Toyota Hilux", "Mitsubishi L200", "Ford Ranger", "Peugeot 208", "MG ZS", "Chery Tiggo 2",
]


class Command(BaseCommand):
    help = "Carga o borra datos de demostración (reservas pasadas) para probar el dashboard."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=90, help="Días hacia atrás a generar (por defecto 90)")
        parser.add_argument("--borrar", action="store_true", help="Elimina los datos demo en vez de crearlos")
        parser.add_argument("--semilla", type=int, default=2026, help="Semilla aleatoria, para datos reproducibles")

    def handle(self, *args, **opciones):
        if opciones["borrar"]:
            self.borrar()
        else:
            self.cargar(opciones["dias"], opciones["semilla"])

    @transaction.atomic
    def borrar(self):
        usuarios = User.objects.filter(username__startswith=PREFIJO)
        reservas = Reserva.objects.filter(usuario__in=usuarios)
        horario_ids = set(reservas.values_list("horario_id", flat=True))
        n_reservas = reservas.count()
        reservas.delete()
        # Horarios que solo tenían reservas demo: se borran (son todos pasados)
        n_horarios, _ = HorarioDisponible.objects.filter(id__in=horario_ids, reservas__isnull=True).delete()
        n_usuarios, _ = usuarios.delete()
        self.stdout.write(self.style.SUCCESS(
            f"Eliminados: {n_reservas} reservas, {n_horarios} horarios y los usuarios demo."
        ))

    @transaction.atomic
    def cargar(self, dias, semilla):
        if User.objects.filter(username__startswith=PREFIJO).exists():
            raise CommandError("Ya hay datos demo cargados. Ejecuta primero: python manage.py datos_demo --borrar")

        precios = list(PrecioServicio.objects.select_related("servicio").filter(servicio__activo=True))
        if not precios:
            raise CommandError("No hay servicios con precio. ¿Aplicaste las migraciones?")

        rnd = random.Random(semilla)
        clientes = []
        for i, (nombre, apellido) in enumerate(NOMBRES):
            usuario = User(
                username=f"{PREFIJO}{i:02d}@demo.invalid",
                email=f"{PREFIJO}{i:02d}@demo.invalid",
                first_name=nombre,
                last_name=apellido,
            )
            usuario.set_unusable_password()  # no se puede iniciar sesión con ellos
            usuario.save()
            # Algunos clientes son habituales: auto y teléfono fijos
            clientes.append((usuario, rnd.choice(AUTOS), f"+56 9 {rnd.randint(1000, 9999)} {rnd.randint(1000, 9999)}"))
        habituales = clientes[:8]

        # Los lavados completos son los más pedidos; los "otros servicios", poco
        pesos = [1 if p.servicio.precio_desde else 6 for p in precios]
        hoy = timezone.localdate()
        creadas = omitidas = 0

        for atras in range(dias, 0, -1):
            fecha = hoy - timedelta(days=atras)
            if fecha.weekday() == 6:  # domingo no se trabaja
                continue
            # Más demanda los sábados y viernes, y crecimiento suave hacia el presente
            base = {5: 0.75, 4: 0.55}.get(fecha.weekday(), 0.4) + 0.15 * (1 - atras / dias)
            for hora in HORAS:
                prob = base + (0.1 if hora.hour in (10, 11, 16) else 0) - (0.15 if hora.hour == 12 else 0)
                if rnd.random() > prob:
                    continue

                horario, _ = HorarioDisponible.objects.get_or_create(fecha=fecha, hora=hora)
                if horario.reservas.exists():  # hay una reserva real en ese turno: no se toca
                    omitidas += 1
                    continue

                usuario, auto, telefono = rnd.choice(habituales) if rnd.random() < 0.45 else rnd.choice(clientes)
                precio = rnd.choices(precios, pesos)[0]
                Reserva.objects.create(
                    usuario=usuario,
                    horario=horario,
                    nombre=f"{usuario.first_name} {usuario.last_name}",
                    email=usuario.email,
                    telefono=telefono,
                    servicio=precio.servicio,
                    tamano_vehiculo=precio.tamano_vehiculo,
                    precio=precio.precio,
                    Marca_modelo_auto=auto,
                    estado=rnd.choices(
                        [EstadoReserva.COMPLETADA, EstadoReserva.CANCELADA, EstadoReserva.NO_ASISTIO, EstadoReserva.PENDIENTE],
                        [84, 9, 5, 2],
                    )[0],
                )
                creadas += 1

        # Las canceladas liberan su horario; como son fechas pasadas, no afecta a nadie
        self.stdout.write(self.style.SUCCESS(
            f"Creados {len(clientes)} clientes demo y {creadas} reservas en los últimos {dias} días"
            + (f" ({omitidas} turnos omitidos por tener reservas reales)." if omitidas else ".")
        ))
        self.stdout.write("Para eliminarlos: python manage.py datos_demo --borrar")
