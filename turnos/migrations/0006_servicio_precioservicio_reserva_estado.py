import django.db.models.deletion
from django.db import migrations, models


TAMANO_CHOICES = [
    ('pequeno', 'Auto Pequeño'),
    ('mediano', 'Auto Mediano'),
    ('grande', 'Auto Grande'),
    ('grande_xl', 'Auto Grande XL'),
    ('unico', 'Precio único'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('turnos', '0005_reserva_marca_modelo_auto'),
    ]

    operations = [
        migrations.CreateModel(
            name='Servicio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, unique=True)),
                ('descripcion', models.CharField(blank=True, default='', max_length=255)),
                ('precio_desde', models.BooleanField(default=False)),
                ('activo', models.BooleanField(default=True)),
                ('orden', models.PositiveSmallIntegerField(default=0)),
            ],
            options={'ordering': ['orden', 'nombre']},
        ),
        migrations.CreateModel(
            name='PrecioServicio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tamano_vehiculo', models.CharField(choices=TAMANO_CHOICES, max_length=20)),
                ('precio', models.PositiveIntegerField(help_text='Precio en pesos chilenos')),
                ('servicio', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='precios', to='turnos.servicio')),
            ],
            options={
                'ordering': ['servicio__orden', 'precio'],
                'unique_together': {('servicio', 'tamano_vehiculo')},
            },
        ),
        migrations.AddField(
            model_name='reserva',
            name='servicio',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reservas', to='turnos.servicio'),
        ),
        migrations.AddField(
            model_name='reserva',
            name='tamano_vehiculo',
            field=models.CharField(blank=True, choices=TAMANO_CHOICES, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='reserva',
            name='precio',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='reserva',
            name='estado',
            field=models.CharField(choices=[('pendiente', 'Pendiente'), ('completada', 'Completada'), ('cancelada', 'Cancelada'), ('no_asistio', 'No asistió')], default='pendiente', max_length=20),
        ),
        # Default para que 0008 se pueda revertir con reservas existentes
        migrations.AlterField(
            model_name='reserva',
            name='tipo_servicio',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='reserva',
            name='horario',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reservas', to='turnos.horariodisponible'),
        ),
    ]
