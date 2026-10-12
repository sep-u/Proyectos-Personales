from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('turnos', '0003_horariodisponible_delete_cliente_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='horario',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='reservas',
                to='turnos.horariodisponible',
            ),
        ),
        migrations.AlterField(
            model_name='reserva',
            name='horario',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='reservas',
                to='turnos.horariodisponible',
            ),
        ),
    ]
