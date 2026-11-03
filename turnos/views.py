from datetime import datetime, timedelta

from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from .forms import RegistroForm, LoginForm
from .models import Reserva
from django.shortcuts import get_object_or_404, redirect
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .models import Reserva, HorarioDisponible, PrecioServicio, Servicio
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
        horario = get_object_or_404(HorarioDisponible, id=horario_id, disponible=True, fecha__gte=timezone.localdate())
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
    # fecha__gte: un horario pasado puede quedar "disponible" si se canceló su reserva
    horarios_disponibles = HorarioDisponible.objects.filter(
        disponible=True, fecha__gte=timezone.localdate()
    ).order_by('fecha', 'hora')
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
        messages.error(request, f"Las reservas solo se pueden cancelar con al menos {Reserva.HORAS_ANTICIPACION} horas de anticipación.")
        return redirect("mis_reservas")

    # No se borra: se marca como cancelada para conservar el historial del dashboard
    reserva.cancelar()
    messages.success(request, "La reserva fue cancelada correctamente.")
    return redirect("mis_reservas")


@login_required
def modificar_reserva(request, reserva_id):
    # usuario=request.user: un cliente solo puede modificar SUS reservas, aunque cambie el id en la URL
    reserva = get_object_or_404(Reserva.objects.select_related("horario"), id=reserva_id, usuario=request.user)
    if not reserva.se_puede_modificar:
        messages.error(request, f"Las reservas solo se pueden modificar con al menos {Reserva.HORAS_ANTICIPACION} horas de anticipación.")
        return redirect("mis_reservas")

    if request.method == "POST":
        nuevo = HorarioDisponible.objects.filter(id=request.POST.get("horario")).first()
        if nuevo is None or nuevo.inicio <= timezone.now():
            messages.error(request, "Elige un horario válido.")
            return redirect("modificar_reserva", reserva_id=reserva.id)
        if not reserva.reprogramar(nuevo):
            messages.error(request, "Ese horario acaba de ser tomado por otra persona. Elige otro.")
            return redirect("modificar_reserva", reserva_id=reserva.id)

        try:
            send_mail(
                "Cambio de reserva - CarWash",
                f"Hola {reserva.nombre},\n\nTu reserva fue cambiada a:\n\n"
                f"📅 Fecha: {nuevo.fecha:%d/%m/%Y}\n⏰ Hora: {nuevo.hora:%H:%M}\n🧽 Servicio: {reserva.servicio_display}\n\n"
                "Saludos,\nEquipo CarWash",
                settings.DEFAULT_FROM_EMAIL, [reserva.email],
            )
        except Exception as e:
            print("❌ Error al enviar el correo:", e)

        messages.success(request, f"Tu reserva quedó para el {nuevo.fecha:%d/%m/%Y} a las {nuevo.hora:%H:%M}.")
        return redirect("mis_reservas")

    # Solo horarios libres que todavía no pasan (hoy puede tener horas que ya pasaron)
    ahora = timezone.localtime()
    horarios = HorarioDisponible.objects.filter(disponible=True, fecha__gte=ahora.date()).exclude(
        fecha=ahora.date(), hora__lte=ahora.time()
    ).order_by("fecha", "hora")
    return render(request, "turnos/modificar_reserva.html", {"reserva": reserva, "horarios": horarios})


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
