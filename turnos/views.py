from datetime import datetime, timedelta

from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from .forms import RegistroForm, LoginForm, GenerarHorariosForm
from .models import Reserva
from django.shortcuts import get_object_or_404, redirect
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .models import Reserva, HorarioDisponible, PrecioServicio, Servicio
from . import metricas
# Create your views here.


def limpiar_horarios_vencidos():
    """Borra horarios cuya fecha ya pasó y que nunca tuvieron reservas.

    Los que tienen reservas (incluidas las canceladas) se conservan: Reserva.horario
    usa PROTECT y ese historial lo necesita el dashboard de staff.
    """
    HorarioDisponible.objects.filter(
        fecha__lt=timezone.localdate(), reservas__isnull=True
    ).delete()


def home(request):
    return render(request, "turnos/home.html")

@login_required
def reservas(request):
    limpiar_horarios_vencidos()
    if request.method == "POST":
        nombre = request.POST.get("nombre")
        email = request.POST.get("email")
        telefono = request.POST.get("telefono")
        precio_servicio_id = request.POST.get("precio_servicio")
        horario_id = request.POST.get("horario")  # antes eran "fecha" y "hora" por separado
        marca_modelo_auto = request.POST.get("marca_modelo_auto")

        if not (nombre and email and telefono and precio_servicio_id and horario_id):
            messages.error(request, "Por favor completa todos los campos.")
            return redirect("reservas")

        # Buscamos el horario y verificamos que siga disponible
        horario = get_object_or_404(HorarioDisponible, id=horario_id, disponible=True)
        precio_servicio = get_object_or_404(
            PrecioServicio.objects.select_related("servicio"), id=precio_servicio_id, servicio__activo=True
        )

        # Guardar la reserva
        Reserva.objects.create(
            usuario=request.user,
            horario=horario,
            nombre=nombre,
            email=email,
            telefono=telefono,
            Marca_modelo_auto=marca_modelo_auto,
            servicio=precio_servicio.servicio,
            tamano_vehiculo=precio_servicio.tamano_vehiculo,
            precio=precio_servicio.precio,
        )

        # Enviar correo de confirmación
        asunto = "Confirmación de reserva - CarWash"
        mensaje = f"""
Hola {nombre},

Tu reserva fue registrada exitosamente. Estos son los detalles:

📅 Fecha: {horario.fecha}
⏰ Hora: {horario.hora}
🧽 Servicio: {precio_servicio}

📍 CarWash - ¡Te esperamos!

Si necesitas cancelar tu reserva, puedes hacerlo desde tu cuenta.

Saludos,
Equipo CarWash
"""
        destinatario = [email]

        try:
            send_mail(asunto, mensaje, settings.DEFAULT_FROM_EMAIL, destinatario)
        except Exception as e:
            print("❌ Error al enviar el correo:", e)

        messages.success(request, "¡Tu reserva fue registrada exitosamente!")
        return redirect("mis_reservas")

     # Para el GET: le pasamos al template solo los horarios disponibles
    horarios_disponibles = HorarioDisponible.objects.filter(disponible=True).order_by('fecha', 'hora')
    servicios = Servicio.objects.filter(activo=True).prefetch_related("precios")
    return render(request, "turnos/reservas.html", {
        "horarios_disponibles": horarios_disponibles,
        "servicios": servicios,
    })


@login_required
@require_POST
def cancelar_reserva(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id, usuario=request.user)
    if not reserva.se_puede_cancelar:
        messages.error(request, "Esta reserva ya no se puede cancelar.")
        return redirect("mis_reservas")

    # No se borra: se marca como cancelada para conservar el historial del dashboard
    reserva.cancelar()
    messages.success(request, "La reserva fue cancelada correctamente.")
    return redirect("mis_reservas")


@login_required
def mis_reservas(request):
    reservas = Reserva.objects.filter(usuario=request.user).order_by("-horario__fecha","-horario__hora")
    return render(request, "turnos/mis_reservas.html", {"reservas": reservas})

def lista_precios(request):
    servicios = Servicio.objects.filter(activo=True).prefetch_related("precios")
    return render(request, "turnos/lista_precios.html", {"servicios": servicios})


def register(request):
    if request.method == "POST":
        form = RegistroForm(request.POST)
        
        if form.is_valid():
            nombre = form.cleaned_data["first_name"]
            apellido = form.cleaned_data["last_name"]
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]

            if User.objects.filter(username=email).exists():
                messages.error(request, "Este correo ya está registrado.")
                return redirect("register")

            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=nombre,
                last_name=apellido
            )

            messages.success(request, "Cuenta creada exitosamente. Inicia sesión.")
            return redirect("login")
    else:
        form = RegistroForm()

    return render(request, "turnos/registro.html", {"form": form})

def login_user(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        # Como usamos email como username
        user = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, "Inicio de sesión exitoso.")
            return redirect("home")  # Ajusta a tu página principal
        else:
            messages.error(request, "Correo o contraseña incorrectos.")
            return redirect("login")
        
    form = LoginForm()
    return render(request, "turnos/login.html", {"form": form})


def logout_user(request):
    logout(request)
    return redirect("home")


@user_passes_test(lambda u: u.is_staff, login_url='login')
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

    hace_una_semana = timezone.localdate() - timedelta(days=7)
    horarios = HorarioDisponible.objects.filter(
        fecha__gte=hace_una_semana
    ).order_by('-fecha', '-hora')[:50]
    return render(request, "turnos/generar_horarios.html", {"form": form, "horarios": horarios})

@user_passes_test(lambda u: u.is_staff, login_url='login')
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
    return render(request, "turnos/dashboard.html", datos)
