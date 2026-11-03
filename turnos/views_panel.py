"""Vistas del panel de administración propio (reemplaza el uso diario de /admin/).

Todas exigen is_staff. Las acciones que modifican datos solo aceptan POST
(con su token CSRF), así un link o una recarga de página nunca cambia nada.
"""
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import metricas
from .forms import (EliminarHorariosForm, GenerarHorariosForm, PrecioServicioFormSet,
                    ReservaPanelForm, ServicioForm)
from .models import EstadoReserva, HorarioDisponible, Reserva, Servicio
from .views import limpiar_horarios_vencidos

staff_required = user_passes_test(lambda u: u.is_staff, login_url='login')

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _volver(request, por_defecto):
    """Redirige a la página desde donde se envió el formulario (campo oculto "next").

    Se valida que sea una URL de este mismo sitio; si no, alguien podría armar un
    link que, tras la acción, mande al admin a una página externa (open redirect).
    """
    destino = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return redirect(destino)
    return redirect(por_defecto)


def _leer_fecha(texto, por_defecto=None):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return por_defecto


# ---------- Agenda del día ----------

@staff_required
def agenda(request):
    hoy = timezone.localdate()
    dia = _leer_fecha(request.GET.get("fecha"), hoy)

    horarios = (
        HorarioDisponible.objects.filter(fecha=dia)
        .prefetch_related("reservas__servicio")
        .order_by("hora")
    )

    # Por cada horario: la reserva "viva" (no cancelada) si existe, y cuántas canceladas tuvo
    filas = []
    for h in horarios:
        reservas = list(h.reservas.all())
        activa = next((r for r in reservas if r.estado != EstadoReserva.CANCELADA), None)
        canceladas = sum(r.estado == EstadoReserva.CANCELADA for r in reservas)
        filas.append({"horario": h, "reserva": activa, "canceladas": canceladas, "borrable": not reservas})

    reservas_dia = Reserva.objects.filter(horario__fecha=dia)
    resumen = reservas_dia.aggregate(
        pendientes=Count("id", filter=Q(estado=EstadoReserva.PENDIENTE)),
        completadas=Count("id", filter=Q(estado=EstadoReserva.COMPLETADA)),
        no_asistio=Count("id", filter=Q(estado=EstadoReserva.NO_ASISTIO)),
        ingresos=Sum("precio", filter=Q(estado=EstadoReserva.COMPLETADA)),
    )
    resumen["libres"] = sum(1 for f in filas if f["reserva"] is None)

    return render(request, "turnos/panel/agenda.html", {
        "dia": dia,
        "nombre_dia": DIAS[dia.weekday()],
        "hoy": hoy,
        "anterior": dia - timedelta(days=1),
        "siguiente": dia + timedelta(days=1),
        "filas": filas,
        "resumen": resumen,
        "hay_borrables": any(f["borrable"] for f in filas),
        "seccion": "agenda",
    })


# ---------- Reservas ----------

@staff_required
def reservas(request):
    hoy = timezone.localdate()
    vista = request.GET.get("vista", "proximas")
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    servicio_id = request.GET.get("servicio", "")
    desde = _leer_fecha(request.GET.get("desde"))
    hasta = _leer_fecha(request.GET.get("hasta"))

    qs = Reserva.objects.select_related("horario", "servicio")

    # Vistas rápidas: lo que el admin revisa más seguido
    if vista == "proximas":
        qs = qs.filter(estado=EstadoReserva.PENDIENTE, horario__fecha__gte=hoy).order_by("horario__fecha", "horario__hora")
    elif vista == "por_marcar":
        qs = qs.filter(estado=EstadoReserva.PENDIENTE, horario__fecha__lt=hoy).order_by("horario__fecha", "horario__hora")
    else:
        vista = "todas"
        qs = qs.order_by("-horario__fecha", "-horario__hora")

    # Filtros adicionales (se combinan con la vista)
    if q:
        qs = qs.filter(
            Q(nombre__icontains=q) | Q(email__icontains=q)
            | Q(telefono__icontains=q) | Q(Marca_modelo_auto__icontains=q)
        )
    if estado in EstadoReserva.values:
        qs = qs.filter(estado=estado)
    if servicio_id.isdigit():
        qs = qs.filter(servicio_id=servicio_id)
    if desde:
        qs = qs.filter(horario__fecha__gte=desde)
    if hasta:
        qs = qs.filter(horario__fecha__lte=hasta)

    pagina = Paginator(qs, 25).get_page(request.GET.get("page"))

    # Para que los links de paginación conserven los filtros activos
    filtros = request.GET.copy()
    filtros.pop("page", None)

    return render(request, "turnos/panel/reservas.html", {
        "pagina": pagina,
        "vista": vista,
        "q": q,
        "estado": estado,
        "servicio_id": servicio_id,
        "desde": desde,
        "hasta": hasta,
        "estados": EstadoReserva.choices,
        "servicios": Servicio.objects.all(),
        "filtros": filtros.urlencode(),
        "conteo_por_marcar": Reserva.objects.filter(estado=EstadoReserva.PENDIENTE, horario__fecha__lt=hoy).count(),
        "seccion": "reservas",
    })


@staff_required
@require_POST
def cambiar_estado(request):
    """Cambia el estado de una o varias reservas (botones por fila y acción masiva)."""
    nuevo = request.POST.get("estado")
    ids = request.POST.getlist("ids")
    if nuevo not in EstadoReserva.values or not ids:
        messages.warning(request, "Selecciona al menos una reserva y una acción.")
        return _volver(request, "panel_reservas")

    cambiadas, rechazadas = 0, 0
    for reserva in Reserva.objects.filter(id__in=ids).select_related("horario"):
        if reserva.cambiar_estado(nuevo):
            cambiadas += 1
        else:
            rechazadas += 1

    etiqueta = EstadoReserva(nuevo).label
    if cambiadas:
        messages.success(request, f"{cambiadas} reserva{'s' if cambiadas != 1 else ''} marcada{'s' if cambiadas != 1 else ''} como \"{etiqueta}\".")
    if rechazadas:
        messages.warning(
            request,
            f"{rechazadas} no se pudo{'ieron' if rechazadas != 1 else ''} cambiar: las canceladas no se reactivan "
            "y los turnos futuros no se pueden marcar como completados o 'no asistió'."
        )
    return _volver(request, "panel_reservas")


@staff_required
def reserva_detalle(request, reserva_id):
    reserva = get_object_or_404(Reserva.objects.select_related("horario", "servicio", "usuario"), id=reserva_id)

    if request.method == "POST":
        form = ReservaPanelForm(request.POST, instance=reserva)
        if form.is_valid():
            form.save()
            messages.success(request, "Datos de la reserva actualizados.")
            return redirect("panel_reserva", reserva_id=reserva.id)
    else:
        form = ReservaPanelForm(instance=reserva)

    # Horarios a los que se puede mover (solo si sigue pendiente)
    horarios_libres = []
    if reserva.estado == EstadoReserva.PENDIENTE:
        horarios_libres = HorarioDisponible.objects.filter(
            disponible=True, fecha__gte=timezone.localdate()
        ).order_by("fecha", "hora")[:300]

    otras = (
        Reserva.objects.filter(usuario=reserva.usuario).exclude(id=reserva.id)
        .select_related("horario", "servicio").order_by("-horario__fecha")[:10]
    )

    acciones = [(valor, etiqueta) for valor, etiqueta in EstadoReserva.choices if reserva.puede_cambiar_a(valor)]

    return render(request, "turnos/panel/reserva_detalle.html", {
        "reserva": reserva,
        "form": form,
        "horarios_libres": horarios_libres,
        "otras": otras,
        "acciones": acciones,
        "hoy": timezone.localdate(),
        "seccion": "reservas",
    })


@staff_required
@require_POST
def reprogramar_reserva(request, reserva_id):
    reserva = get_object_or_404(Reserva.objects.select_related("horario"), id=reserva_id)
    nuevo = get_object_or_404(HorarioDisponible, id=request.POST.get("horario"))

    if reserva.estado != EstadoReserva.PENDIENTE:
        messages.error(request, "Solo se pueden reprogramar reservas pendientes.")
    elif nuevo.fecha < timezone.localdate():
        messages.error(request, "No se puede mover una reserva a una fecha pasada.")
    elif reserva.reprogramar(nuevo):
        messages.success(request, f"Reserva movida al {nuevo.fecha:%d/%m/%Y} a las {nuevo.hora:%H:%M}.")
    else:
        messages.error(request, "Ese horario acaba de ser tomado por otra reserva. Elige otro.")
    return redirect("panel_reserva", reserva_id=reserva.id)


# ---------- Horarios ----------

@staff_required
def generar_horarios(request):
    limpiar_horarios_vencidos()
    if request.method == "POST":
        form = GenerarHorariosForm(request.POST)
        if form.is_valid():
            fecha_inicio = form.cleaned_data["fecha_inicio"]
            fecha_fin = form.cleaned_data["fecha_fin"]
            hora_inicio = form.cleaned_data["hora_inicio"]
            hora_fin = form.cleaned_data["hora_fin"]
            intervalo_minutos = form.cleaned_data["intervalo_minutos"]
            dias_semana = {int(d) for d in form.cleaned_data["dias_semana"]}

            creados = 0
            fecha = fecha_inicio
            while fecha <= fecha_fin:
                if fecha.weekday() in dias_semana:
                    hora_actual = datetime.combine(fecha, hora_inicio)
                    limite = datetime.combine(fecha, hora_fin)
                    while hora_actual < limite:
                        _, created = HorarioDisponible.objects.get_or_create(
                            fecha=fecha,
                            hora=hora_actual.time(),
                        )
                        if created:
                            creados += 1
                        hora_actual += timedelta(minutes=intervalo_minutos)
                fecha += timedelta(days=1)

            messages.success(request, f"Se generaron {creados} horarios nuevos.")
            return redirect("generar_horarios")
    else:
        form = GenerarHorariosForm()

    # Resumen de los próximos 14 días: cuántos turnos hay generados y cuántos están tomados
    hoy = timezone.localdate()
    conteos = {
        f["fecha"]: f for f in
        HorarioDisponible.objects.filter(fecha__range=(hoy, hoy + timedelta(days=13)))
        .values("fecha").annotate(total=Count("id"), ocupados=Count("id", filter=Q(disponible=False)))
    }
    proximos_dias = []
    for i in range(14):
        d = hoy + timedelta(days=i)
        c = conteos.get(d, {})
        proximos_dias.append({"fecha": d, "nombre": DIAS[d.weekday()], "total": c.get("total", 0), "ocupados": c.get("ocupados", 0)})

    return render(request, "turnos/panel/horarios.html", {
        "form": form,
        "form_eliminar": EliminarHorariosForm(),
        "proximos_dias": proximos_dias,
        "seccion": "horarios",
    })


@staff_required
@require_POST
def eliminar_horario(request, horario_id):
    horario = get_object_or_404(HorarioDisponible, id=horario_id)
    if horario.reservas.exists():
        messages.error(request, "Ese horario tiene reservas asociadas y no se puede eliminar.")
    else:
        horario.delete()
        messages.success(request, f"Horario de las {horario.hora:%H:%M} eliminado.")
    return _volver(request, "panel_agenda")


@staff_required
@require_POST
def eliminar_horarios_libres(request):
    """Borra los horarios SIN reservas de un rango de fechas (ej. un feriado o vacaciones)."""
    form = EliminarHorariosForm(request.POST)
    if form.is_valid():
        borrados, _ = HorarioDisponible.objects.filter(
            fecha__range=(form.cleaned_data["fecha_inicio"], form.cleaned_data["fecha_fin"]),
            reservas__isnull=True,
        ).delete()
        messages.success(request, f"Se eliminaron {borrados} horarios libres. Los que tienen reservas se conservaron.")
    else:
        for error in form.errors.values():
            messages.error(request, error.as_text())
    return _volver(request, "generar_horarios")


# ---------- Servicios y precios ----------

@staff_required
def servicios(request):
    lista = Servicio.objects.prefetch_related("precios").annotate(total_reservas=Count("reservas"))
    return render(request, "turnos/panel/servicios.html", {"servicios": lista, "seccion": "servicios"})


@staff_required
def servicio_editar(request, servicio_id=None):
    servicio = get_object_or_404(Servicio, id=servicio_id) if servicio_id else Servicio()

    if request.method == "POST":
        form = ServicioForm(request.POST, instance=servicio)
        formset = PrecioServicioFormSet(request.POST, instance=servicio)
        if form.is_valid() and formset.is_valid():
            # atomic: o se guarda el servicio con todos sus precios, o nada
            with transaction.atomic():
                servicio = form.save()
                formset.instance = servicio
                formset.save()
            messages.success(request, f"Servicio \"{servicio.nombre}\" guardado.")
            return redirect("panel_servicios")
    else:
        form = ServicioForm(instance=servicio)
        formset = PrecioServicioFormSet(instance=servicio)

    return render(request, "turnos/panel/servicio_form.html", {
        "form": form,
        "formset": formset,
        "servicio": servicio,
        "seccion": "servicios",
    })


@staff_required
@require_POST
def servicio_activar(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id)
    servicio.activo = not servicio.activo
    servicio.save(update_fields=["activo"])
    estado = "visible para los clientes" if servicio.activo else "oculto para los clientes"
    messages.success(request, f"\"{servicio.nombre}\" ahora está {estado}.")
    return redirect("panel_servicios")


# ---------- Dashboard ----------

@staff_required
def dashboard_staff(request):
    try:
        dias = int(request.GET.get("periodo", 30))
    except ValueError:
        dias = 30
    if dias not in metricas.PERIODOS:
        dias = 30

    datos = metricas.calcular(dias)
    datos["dias"] = dias
    datos["periodos"] = metricas.PERIODOS
    datos["graficos"] = {
        "tendencia": datos["tendencia"],
        "servicios": datos["servicios"],
        "por_hora": datos["por_hora"],
        "por_dia": datos["por_dia"],
    }
    datos["seccion"] = "dashboard"
    return render(request, "turnos/dashboard.html", datos)
