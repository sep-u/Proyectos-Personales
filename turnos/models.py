from datetime import datetime

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class HorarioDisponible(models.Model):
    fecha = models.DateField()
    hora = models.TimeField()
    disponible = models.BooleanField(default=True)

    class Meta:
        unique_together = ('fecha', 'hora')
        ordering = ['fecha', 'hora']

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

    def _liberar_horario(self):
        """Deja el horario disponible si ya no tiene otra reserva pendiente."""
        if not self.horario.reservas.filter(estado=EstadoReserva.PENDIENTE).exists():
            self.horario.disponible = True
            self.horario.save(update_fields=['disponible'])

    @property
    def se_puede_cancelar(self):
        if self.estado != EstadoReserva.PENDIENTE:
            return False
        inicio = timezone.make_aware(datetime.combine(self.horario.fecha, self.horario.hora))
        return inicio > timezone.now()

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
