from datetime import datetime, timedelta

from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone


class HorarioDisponible(models.Model):
    fecha = models.DateField()
    hora = models.TimeField()
    disponible = models.BooleanField(default=True)

    class Meta:
        unique_together = ('fecha', 'hora')
        ordering = ['fecha', 'hora']

    @property
    def inicio(self):
        """Fecha + hora juntas, con zona horaria (para comparar con timezone.now())."""
        return timezone.make_aware(datetime.combine(self.fecha, self.hora))

    def __str__(self):
        estado = "Disponible" if self.disponible else "Ocupado"
        return f"{self.fecha} {self.hora} - {estado}"


class Servicio(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=255, blank=True, default='')
    # True cuando el precio publicado es un mínimo ("Desde $10.000")
    precio_desde = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'nombre']

    def __str__(self):
        return self.nombre


class TamanoVehiculo(models.TextChoices):
    PEQUENO = 'pequeno', 'Auto Pequeño'
    MEDIANO = 'mediano', 'Auto Mediano'
    GRANDE = 'grande', 'Auto Grande'
    GRANDE_XL = 'grande_xl', 'Auto Grande XL'
    UNICO = 'unico', 'Precio único'


class PrecioServicio(models.Model):
    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name='precios')
    tamano_vehiculo = models.CharField(max_length=20, choices=TamanoVehiculo.choices)
    precio = models.PositiveIntegerField(help_text="Precio en pesos chilenos")

    class Meta:
        unique_together = ('servicio', 'tamano_vehiculo')
        ordering = ['servicio__orden', 'precio']

    def __str__(self):
        if self.tamano_vehiculo == TamanoVehiculo.UNICO:
            return self.servicio.nombre
        return f"{self.servicio.nombre} - {self.get_tamano_vehiculo_display()}"


class EstadoReserva(models.TextChoices):
    PENDIENTE = 'pendiente', 'Pendiente'
    COMPLETADA = 'completada', 'Completada'
    CANCELADA = 'cancelada', 'Cancelada'
    NO_ASISTIO = 'no_asistio', 'No asistió'


class Reserva(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    # PROTECT: borrar un horario con reservas debe fallar en vez de borrar el historial
    horario = models.ForeignKey(HorarioDisponible, on_delete=models.PROTECT, related_name='reservas')
    nombre = models.CharField(max_length=100)
    email = models.EmailField()
    telefono = models.CharField(max_length=20)
    # servicio/tamano/precio son null solo en reservas antiguas (antes de la migración 0006)
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, null=True, blank=True, related_name='reservas')
    tamano_vehiculo = models.CharField(max_length=20, choices=TamanoVehiculo.choices, blank=True, default='')
    # Copia del precio al momento de reservar, para que cambiar la lista de precios no altere el historial
    precio = models.PositiveIntegerField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=EstadoReserva.choices, default=EstadoReserva.PENDIENTE)
    Marca_modelo_auto = models.CharField(max_length=100, blank=True, default='')
    creado = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.horario.disponible = False
            self.horario.save()
        super().save(*args, **kwargs)
        # Cubre también cambios de estado hechos desde el admin
        if self.estado == EstadoReserva.CANCELADA:
            self._liberar_horario()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self._liberar_horario()

    def _liberar_horario(self, horario=None):
        """Deja el horario disponible si ya no tiene otra reserva pendiente."""
        horario = horario or self.horario
        if not horario.reservas.filter(estado=EstadoReserva.PENDIENTE).exists():
            horario.disponible = True
            horario.save(update_fields=['disponible'])

    def puede_cambiar_a(self, nuevo_estado):
        """Reglas para los cambios de estado hechos por el staff desde el panel."""
        if nuevo_estado == self.estado or nuevo_estado not in EstadoReserva.values:
            return False
        # Una cancelada no se reactiva: su horario ya pudo haberlo tomado otra persona
        if self.estado == EstadoReserva.CANCELADA:
            return False
        # No se puede marcar como atendido un turno que todavía no llega
        if nuevo_estado in (EstadoReserva.COMPLETADA, EstadoReserva.NO_ASISTIO):
            return self.horario.fecha <= timezone.localdate()
        return True

    def cambiar_estado(self, nuevo_estado):
        if not self.puede_cambiar_a(nuevo_estado):
            return False
        if nuevo_estado == EstadoReserva.CANCELADA:
            self.cancelar()
        else:
            self.estado = nuevo_estado
            self.save(update_fields=['estado'])
        return True

    @transaction.atomic
    def reprogramar(self, nuevo_horario):
        """Mueve una reserva pendiente a otro horario libre. Devuelve False si ya no estaba libre."""
        # filter().update() es una sola consulta: si dos personas toman el mismo horario
        # a la vez, solo a una le actualiza 1 fila; la otra recibe 0 y no se pisan.
        tomado = HorarioDisponible.objects.filter(pk=nuevo_horario.pk, disponible=True).update(disponible=False)
        if not tomado:
            return False
        anterior = self.horario
        self.horario = nuevo_horario
        self.save(update_fields=['horario'])
        self._liberar_horario(anterior)
        return True

    # Anticipación mínima para que el cliente cancele o modifique su reserva
    HORAS_ANTICIPACION = 12

    @property
    def dentro_del_plazo(self):
        """True si es pendiente y faltan al menos HORAS_ANTICIPACION horas para el turno."""
        if self.estado != EstadoReserva.PENDIENTE:
            return False
        return self.horario.inicio - timezone.now() >= timedelta(hours=self.HORAS_ANTICIPACION)

    @property
    def se_puede_cancelar(self):
        return self.dentro_del_plazo

    @property
    def se_puede_modificar(self):
        return self.dentro_del_plazo

    def cancelar(self):
        self.estado = EstadoReserva.CANCELADA
        self.save(update_fields=['estado'])

    @property
    def servicio_display(self):
        if not self.servicio:
            return "—"
        if self.tamano_vehiculo and self.tamano_vehiculo != TamanoVehiculo.UNICO:
            return f"{self.servicio.nombre} ({self.get_tamano_vehiculo_display()})"
        return self.servicio.nombre

    def __str__(self):
        return f"{self.nombre} - {self.servicio_display} ({self.horario.fecha} {self.horario.hora})"
