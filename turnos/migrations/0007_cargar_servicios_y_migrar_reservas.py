"""Carga la lista de precios real (antes escrita a mano en lista_precios.html)
y enlaza las reservas existentes, que solo tenían `tipo_servicio` como texto."""

from django.db import migrations
from django.utils import timezone


TAMANOS = ['pequeno', 'mediano', 'grande', 'grande_xl']

# (nombre, descripcion, precio_desde, precios por tamaño o precio único)
SERVICIOS = [
    ('Lavado Exterior', '', False, [6000, 8000, 10000, 12000]),
    ('Lavado Interior', 'Incluye aspirado, limpieza de superficies, vidrios y aromatizante.', False, [7000, 9000, 11000, 13000]),
    ('Lavado Básico', 'Incluye lavado exterior e interior, cera en aerosol y aspirado de maletero.', False, [10000, 12000, 14000, 16000]),
    ('Lavado Full', 'Incluye lavado exterior e interior con silicona, cera premium, aspirado de maletero y tapices.', False, [12000, 14000, 16000, 18000]),
    ('Pulido de Focos', '', True, 10000),
    ('Alfombras de Hogar', '', True, 8000),
    ('Tapiz', '', True, 8000),
]

# Valores que enviaba el <select> de reservas.html antes de este cambio
TEXTO_A_SERVICIO = {
    'lavado exterior': 'Lavado Exterior',
    'lavado interior': 'Lavado Interior',
    'lavado basico': 'Lavado Básico',
    'lavado básico': 'Lavado Básico',
    'lavado full': 'Lavado Full',
    'pulido': 'Pulido de Focos',
    'pulido de focos': 'Pulido de Focos',
    'tapiz': 'Tapiz',
    'alfombras de hogar': 'Alfombras de Hogar',
}


def cargar(apps, schema_editor):
    Servicio = apps.get_model('turnos', 'Servicio')
    PrecioServicio = apps.get_model('turnos', 'PrecioServicio')
    Reserva = apps.get_model('turnos', 'Reserva')

    servicios = {}
    for orden, (nombre, descripcion, precio_desde, precios) in enumerate(SERVICIOS):
        servicio, _ = Servicio.objects.get_or_create(
            nombre=nombre,
            defaults={'descripcion': descripcion, 'precio_desde': precio_desde, 'orden': orden},
        )
        servicios[nombre] = servicio
        if isinstance(precios, list):
            for tamano, precio in zip(TAMANOS, precios):
                PrecioServicio.objects.get_or_create(servicio=servicio, tamano_vehiculo=tamano, defaults={'precio': precio})
        else:
            PrecioServicio.objects.get_or_create(servicio=servicio, tamano_vehiculo='unico', defaults={'precio': precios})

    # Reservas antiguas: se sabe el servicio pero no el tamaño del vehículo,
    # así que tamano_vehiculo y precio quedan vacíos (el dashboard las mostrará como "sin dato").
    hoy = timezone.localdate()
    for reserva in Reserva.objects.select_related('horario'):
        nombre = TEXTO_A_SERVICIO.get((reserva.tipo_servicio or '').strip().lower())
        if nombre:
            reserva.servicio = servicios[nombre]
            if servicios[nombre].precios.filter(tamano_vehiculo='unico').exists():
                reserva.tamano_vehiculo = 'unico'
                reserva.precio = servicios[nombre].precios.get(tamano_vehiculo='unico').precio
        # Antes no existía el estado: las reservas pasadas se asumen realizadas
        if reserva.horario.fecha < hoy:
            reserva.estado = 'completada'
        reserva.save(update_fields=['servicio', 'tamano_vehiculo', 'precio', 'estado'])


def revertir(apps, schema_editor):
    Reserva = apps.get_model('turnos', 'Reserva')
    for reserva in Reserva.objects.select_related('servicio'):
        if reserva.servicio:
            reserva.tipo_servicio = reserva.servicio.nombre
            reserva.save(update_fields=['tipo_servicio'])


class Migration(migrations.Migration):

    dependencies = [
        ('turnos', '0006_servicio_precioservicio_reserva_estado'),
    ]

    operations = [
        migrations.RunPython(cargar, revertir),
    ]
