from django.contrib import admin
from .models import HorarioDisponible, Reserva, Servicio, PrecioServicio, EstadoReserva


@admin.register(HorarioDisponible)
class HorarioDisponibleAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'hora', 'disponible')
    list_filter = ('disponible', 'fecha')
    ordering = ('fecha', 'hora')


class PrecioServicioInline(admin.TabularInline):
    model = PrecioServicio
    extra = 0


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio_desde', 'activo', 'orden')
    list_editable = ('activo', 'orden')
    inlines = [PrecioServicioInline]


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'email', 'servicio', 'tamano_vehiculo', 'precio', 'estado', 'horario', 'creado')
    list_filter = ('estado', 'servicio', 'tamano_vehiculo')
    list_editable = ('estado',)
    ordering = ('-creado',)
    actions = ['marcar_completadas', 'marcar_no_asistio', 'cancelar_reservas']

    @admin.action(description="Marcar como completadas")
    def marcar_completadas(self, request, queryset):
        for reserva in queryset:
            reserva.estado = EstadoReserva.COMPLETADA
            reserva.save(update_fields=['estado'])

    @admin.action(description="Marcar como 'no asistió'")
    def marcar_no_asistio(self, request, queryset):
        for reserva in queryset:
            reserva.estado = EstadoReserva.NO_ASISTIO
            reserva.save(update_fields=['estado'])

    @admin.action(description="Cancelar reservas (libera el horario)")
    def cancelar_reservas(self, request, queryset):
        for reserva in queryset:
            reserva.cancelar()
