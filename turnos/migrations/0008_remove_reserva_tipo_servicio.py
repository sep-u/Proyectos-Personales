from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('turnos', '0007_cargar_servicios_y_migrar_reservas'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='reserva',
            name='tipo_servicio',
        ),
    ]
