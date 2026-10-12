"""Cálculo de métricas del negocio para el dashboard de staff.

Todas las métricas se agrupan por la fecha del turno (horario.fecha), no por la
fecha en que se hizo la reserva.
"""
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import ExtractIsoWeekDay, TruncWeek
from django.utils import timezone

from .models import EstadoReserva, HorarioDisponible, Reserva

PERIODOS = {7: "Últimos 7 días", 30: "Últimos 30 días", 90: "Últimos 90 días"}
DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

# Reservas que ocuparon (u ocupan) un turno: todo menos las canceladas
NO_CANCELADAS = ~Q(estado=EstadoReserva.CANCELADA)
COMPLETADAS = Q(estado=EstadoReserva.COMPLETADA)


def _variacion(actual, anterior):
    """Variación porcentual; None si no hay base para comparar."""
    if not anterior:
        return None
    return round((actual - anterior) * 100 / anterior)


def _resumen(qs):
    return qs.aggregate(
        total=Count("id"),
        activas=Count("id", filter=NO_CANCELADAS),
        completadas=Count("id", filter=COMPLETADAS),
        canceladas=Count("id", filter=Q(estado=EstadoReserva.CANCELADA)),
        no_asistio=Count("id", filter=Q(estado=EstadoReserva.NO_ASISTIO)),
        ingresos=Sum("precio", filter=COMPLETADAS),
        completadas_con_precio=Count("id", filter=COMPLETADAS & Q(precio__isnull=False)),
    )


def calcular(dias):
    hoy = timezone.localdate()
    inicio = hoy - timedelta(days=dias - 1)
    inicio_anterior = inicio - timedelta(days=dias)

    periodo = Reserva.objects.filter(horario__fecha__range=(inicio, hoy))
    anterior = Reserva.objects.filter(horario__fecha__range=(inicio_anterior, inicio - timedelta(days=1)))
    act, ant = _resumen(periodo), _resumen(anterior)
    act["ingresos"] = act["ingresos"] or 0
    ant["ingresos"] = ant["ingresos"] or 0

    ticket = act["ingresos"] // act["completadas_con_precio"] if act["completadas_con_precio"] else None
    atendidas = act["completadas"] + act["no_asistio"]

    # Ocupación: solo hacia adelante, porque los horarios pasados sin reserva se borran
    proximos = HorarioDisponible.objects.filter(fecha__range=(hoy, hoy + timedelta(days=6)))
    total_proximos = proximos.count()
    ocupados_proximos = proximos.filter(disponible=False).count()

    por_cobrar = Reserva.objects.filter(
        estado=EstadoReserva.PENDIENTE, horario__fecha__gte=hoy
    ).aggregate(total=Sum("precio"))["total"] or 0

    # Clientes del período que nunca habían reservado antes
    clientes = set(periodo.filter(NO_CANCELADAS).values_list("usuario_id", flat=True))
    recurrentes = set(
        Reserva.objects.filter(usuario_id__in=clientes, horario__fecha__lt=inicio)
        .filter(NO_CANCELADAS).values_list("usuario_id", flat=True)
    )

    kpis = {
        "reservas": act["activas"],
        "reservas_var": _variacion(act["activas"], ant["activas"]),
        "ingresos": act["ingresos"],
        "ingresos_var": _variacion(act["ingresos"], ant["ingresos"]),
        "ticket": ticket,
        "cancelacion": round(act["canceladas"] * 100 / act["total"]) if act["total"] else None,
        "canceladas": act["canceladas"],
        "no_asistio_pct": round(act["no_asistio"] * 100 / atendidas) if atendidas else None,
        "no_asistio": act["no_asistio"],
        "ocupacion": round(ocupados_proximos * 100 / total_proximos) if total_proximos else None,
        "ocupados_proximos": ocupados_proximos,
        "total_proximos": total_proximos,
        "por_cobrar": por_cobrar,
        "clientes": len(clientes),
        "clientes_nuevos": len(clientes - recurrentes),
        "clientes_recurrentes": len(recurrentes),
        "sin_precio": periodo.filter(COMPLETADAS, precio__isnull=True).count(),
    }

    return {
        "hoy": hoy,
        "inicio": inicio,
        "kpis": kpis,
        "tendencia": _tendencia(periodo, inicio, hoy, dias),
        "servicios": _por_servicio(periodo),
        "por_hora": _por_hora(periodo),
        "por_dia": _por_dia_semana(periodo),
        "por_marcar": Reserva.objects.filter(estado=EstadoReserva.PENDIENTE, horario__fecha__lt=hoy).count(),
        "proximas": (
            Reserva.objects.filter(estado=EstadoReserva.PENDIENTE, horario__fecha__range=(hoy, hoy + timedelta(days=1)))
            .select_related("horario", "servicio").order_by("horario__fecha", "horario__hora")
        ),
        "frecuentes": (
            Reserva.objects.filter(COMPLETADAS).values("usuario__username", "nombre")
            .annotate(visitas=Count("id"), gastado=Sum("precio")).order_by("-visitas", "-gastado")[:5]
        ),
    }


def _tendencia(periodo, inicio, hoy, dias):
    """Reservas e ingresos por día (7 y 30 días) o por semana (90 días), rellenando con ceros."""
    if dias <= 30:
        filas = periodo.values("horario__fecha").annotate(
            reservas=Count("id", filter=NO_CANCELADAS), ingresos=Sum("precio", filter=COMPLETADAS)
        )
        datos = {f["horario__fecha"]: f for f in filas}
        fechas = [inicio + timedelta(days=i) for i in range(dias)]
        etiqueta = lambda d: d.strftime("%d/%m")
    else:
        filas = periodo.annotate(semana=TruncWeek("horario__fecha")).values("semana").annotate(
            reservas=Count("id", filter=NO_CANCELADAS), ingresos=Sum("precio", filter=COMPLETADAS)
        )
        datos = {f["semana"]: f for f in filas}
        lunes = inicio - timedelta(days=inicio.weekday())
        fechas = [lunes + timedelta(weeks=i) for i in range((hoy - lunes).days // 7 + 1)]
        etiqueta = lambda d: "Sem. " + d.strftime("%d/%m")

    return [
        {
            "etiqueta": etiqueta(f),
            "reservas": datos.get(f, {}).get("reservas") or 0,
            "ingresos": datos.get(f, {}).get("ingresos") or 0,
        }
        for f in fechas
    ]


def _por_servicio(periodo):
    filas = (
        periodo.filter(NO_CANCELADAS, servicio__isnull=False)
        .values("servicio__nombre")
        .annotate(reservas=Count("id"), ingresos=Sum("precio", filter=COMPLETADAS))
        .order_by("-reservas", "servicio__nombre")
    )
    return [
        {"etiqueta": f["servicio__nombre"], "reservas": f["reservas"], "ingresos": f["ingresos"] or 0}
        for f in filas
    ]


def _por_hora(periodo):
    filas = periodo.filter(NO_CANCELADAS).values("horario__hora").annotate(reservas=Count("id")).order_by("horario__hora")
    return [{"etiqueta": f["horario__hora"].strftime("%H:%M"), "reservas": f["reservas"]} for f in filas]


def _por_dia_semana(periodo):
    filas = periodo.filter(NO_CANCELADAS).annotate(dia=ExtractIsoWeekDay("horario__fecha")).values("dia").annotate(reservas=Count("id"))
    datos = {f["dia"]: f["reservas"] for f in filas}
    # Domingo solo aparece si hubo reservas (normalmente no se trabaja)
    dias = range(1, 8) if datos.get(7) else range(1, 7)
    return [{"etiqueta": DIAS_SEMANA[d - 1], "reservas": datos.get(d, 0)} for d in dias]
