from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .forms import RegistroForm, LoginForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Reserva
from django.shortcuts import get_object_or_404, redirect
from django.core.mail import send_mail
from django.conf import settings
# Create your views here.

def home(request):
    return HttpResponse("Bienvenido al sistema de gestion de turnos del Carwash")

def home(request):
    return render(request, "turnos/home.html")

def reservas(request):
    if request.method == "POST":
        nombre = request.POST.get("nombre")
        email = request.POST.get("email")
        telefono = request.POST.get("telefono")
        tipo_servicio = request.POST.get("tipo_servicio")
        fecha = request.POST.get("fecha")
        hora = request.POST.get("hora")

        if not (nombre and email and telefono and tipo_servicio and fecha and hora):
            messages.error(request, "Por favor completa todos los campos.")
            return redirect("reservas")

        # Guardar la reserva
        Reserva.objects.create(
            usuario=request.user,
            nombre=nombre,
            email=email,
            telefono=telefono,
            tipo_servicio=tipo_servicio,
            fecha=fecha,
            hora=hora,
        )

        # Enviar correo de confirmación
        asunto = "Confirmación de reserva - CarWash"
        mensaje = f"""
Hola {nombre},

Tu reserva fue registrada exitosamente. Estos son los detalles:

📅 Fecha: {fecha}
⏰ Hora: {hora}
🧽 Servicio: {tipo_servicio}

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

    return render(request, "turnos/reservas.html")


def eliminar_reserva(request, reserva_id):
    if not request.user.is_authenticated:
        messages.error(request, "Debes iniciar sesión para eliminar una reserva.")
        return redirect("login")

    reserva = get_object_or_404(Reserva, id=reserva_id, usuario=request.user)
    reserva.delete()
    messages.success(request, "La reserva fue eliminada correctamente.")
    return redirect("mis_reservas")


@login_required
def mis_reservas(request):
    reservas = Reserva.objects.filter(usuario=request.user).order_by("-fecha")
    return render(request, "turnos/mis_reservas.html", {"reservas": reservas})

def lista_precios(request):
    return render(request, "turnos/lista_precios.html")


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