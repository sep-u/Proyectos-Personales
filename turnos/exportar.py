"""Exportación del dashboard a Excel (.xlsx) con openpyxl.

Reutiliza exactamente los mismos datos que muestra el dashboard (metricas.calcular),
así el Excel y la pantalla nunca muestran números distintos.
"""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import Reserva

FORMATO_PESOS = '"$"#,##0'
FORMATO_PCT = '0"%"'
ENCABEZADO_FONDO = PatternFill("solid", fgColor="2A78D6")
ENCABEZADO_FUENTE = Font(bold=True, color="FFFFFF")


def _hoja_tabla(wb, titulo, columnas, filas, formatos=None):
    """Crea una hoja con encabezado con estilo, filas de datos y anchos de columna ajustados.

    formatos: {índice_columna: formato_numérico} para pesos, porcentajes, etc.
    """
    ws = wb.create_sheet(titulo)
    ws.append(columnas)
    for celda in ws[1]:
        celda.fill = ENCABEZADO_FONDO
        celda.font = ENCABEZADO_FUENTE
        celda.alignment = Alignment(horizontal="center")
    for fila in filas:
        ws.append(fila)

    for col, formato in (formatos or {}).items():
        for (celda,) in ws.iter_rows(min_row=2, min_col=col + 1, max_col=col + 1):
            celda.number_format = formato

    for i, nombre in enumerate(columnas, start=1):
        largo = max([len(str(nombre))] + [len(str(f[i - 1])) for f in filas if f[i - 1] is not None])
        ws.column_dimensions[get_column_letter(i)].width = min(largo + 3, 45)
    ws.freeze_panes = "A2"  # el encabezado queda fijo al hacer scroll
    return ws


def _hoja_resumen(wb, datos):
    ws = wb.active
    ws.title = "Resumen"
    k = datos["kpis"]

    ws["A1"] = "Dashboard del negocio – CarWash"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Período: {datos['inicio']:%d/%m/%Y} – {datos['hoy']:%d/%m/%Y} (según la fecha del turno)"
    ws["A2"].font = Font(italic=True, color="52514E")

    # (etiqueta, valor, formato). None = "sin datos" en el dashboard.
    filas = [
        ("Reservas (no canceladas)", k["reservas"], None),
        ("Variación vs. período anterior", k["reservas_var"], FORMATO_PCT),
        ("Ingresos (completadas)", k["ingresos"], FORMATO_PESOS),
        ("Variación de ingresos", k["ingresos_var"], FORMATO_PCT),
        ("Ticket promedio", k["ticket"], FORMATO_PESOS),
        ("Tasa de cancelación", k["cancelacion"], FORMATO_PCT),
        ("Canceladas", k["canceladas"], None),
        ("Tasa de no asistencia", k["no_asistio_pct"], FORMATO_PCT),
        ("No asistió", k["no_asistio"], None),
        ("Ocupación próximos 7 días", k["ocupacion"], FORMATO_PCT),
        ("Turnos ocupados / totales (7 días)", f"{k['ocupados_proximos']} / {k['total_proximos']}", None),
        ("Por cobrar (pendientes futuras)", k["por_cobrar"], FORMATO_PESOS),
        ("Clientes", k["clientes"], None),
        ("Clientes nuevos", k["clientes_nuevos"], None),
        ("Clientes recurrentes", k["clientes_recurrentes"], None),
        ("Completadas sin precio", k["sin_precio"], None),
        ("Reservas pasadas por marcar", datos["por_marcar"], None),
    ]
    ws.append([])
    ws.append(["Indicador", "Valor"])
    for celda in ws[4]:
        celda.fill = ENCABEZADO_FONDO
        celda.font = ENCABEZADO_FUENTE
    for etiqueta, valor, formato in filas:
        ws.append([etiqueta, "—" if valor is None else valor])
        celda = ws.cell(row=ws.max_row, column=2)
        celda.alignment = Alignment(horizontal="right")
        if formato and valor is not None:
            celda.number_format = formato

    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 18


def _hoja_reservas(wb, datos):
    reservas = (
        Reserva.objects.filter(horario__fecha__range=(datos["inicio"], datos["hoy"]))
        .select_related("horario", "servicio", "usuario")
        .order_by("horario__fecha", "horario__hora")
    )
    filas = [
        [
            r.horario.fecha,
            r.horario.hora.strftime("%H:%M"),
            r.nombre,
            r.usuario.username,
            r.email,
            r.telefono,
            r.servicio.nombre if r.servicio else "",
            r.get_tamano_vehiculo_display(),
            r.Marca_modelo_auto,
            r.precio,
            r.get_estado_display(),
        ]
        for r in reservas
    ]
    ws = _hoja_tabla(
        wb, "Reservas",
        ["Fecha", "Hora", "Nombre", "Usuario", "Email", "Teléfono", "Servicio",
         "Tamaño", "Vehículo", "Precio", "Estado"],
        filas, {0: "DD/MM/YYYY", 9: FORMATO_PESOS},
    )
    ws.column_dimensions["A"].width = 12
    ws.auto_filter.ref = ws.dimensions  # flechas de filtro en el encabezado


def construir_excel(datos):
    """Recibe el dict de metricas.calcular() y devuelve el archivo .xlsx en bytes."""
    wb = Workbook()
    _hoja_resumen(wb, datos)

    _hoja_tabla(wb, "Tendencia", ["Fecha / Semana", "Reservas", "Ingresos"],
                [[t["etiqueta"], t["reservas"], t["ingresos"]] for t in datos["tendencia"]],
                {2: FORMATO_PESOS})
    _hoja_tabla(wb, "Por servicio", ["Servicio", "Reservas", "Ingresos"],
                [[s["etiqueta"], s["reservas"], s["ingresos"]] for s in datos["servicios"]],
                {2: FORMATO_PESOS})
    _hoja_tabla(wb, "Por hora", ["Hora", "Reservas"],
                [[h["etiqueta"], h["reservas"]] for h in datos["por_hora"]])
    _hoja_tabla(wb, "Por día", ["Día", "Reservas"],
                [[d["etiqueta"], d["reservas"]] for d in datos["por_dia"]])
    _hoja_tabla(wb, "Clientes frecuentes", ["Nombre", "Usuario", "Visitas", "Total gastado"],
                [[c["nombre"], c["usuario__username"], c["visitas"], c["gastado"] or 0]
                 for c in datos["frecuentes"]],
                {3: FORMATO_PESOS})
    _hoja_reservas(wb, datos)

    salida = BytesIO()
    wb.save(salida)
    return salida.getvalue()
