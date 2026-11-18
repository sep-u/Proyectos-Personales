"""CP-16: prueba de carga con Locust (meta: percentil 95 de respuesta < 3 segundos).

Cada usuario simulado se registra con una cuenta propia, inicia sesión y luego
navega como un cliente: inicio, lista de precios, formulario de reservas y
"Mis reservas". No crea reservas, para no ocupar horarios reales en la base de
datos (las reservas simultáneas ya se prueban en CP-06).

Instalación (solo en tu PC, no hace falta en el servidor):
    pip install locust==2.47.0 waitress==3.0.2

1) En una terminal, levantar el sitio con waitress (servidor WSGI de producción).
   No usar runserver: crea un hilo nuevo por petición, no reutiliza conexiones a
   la base de datos y Django advierte que no sirve para medir rendimiento.
    waitress-serve --listen=127.0.0.1:8000 --threads=16 carwash_proyecto.wsgi:application

2) En otra terminal, ejecutar la prueba:
    locust -f pruebas/locustfile.py --host http://127.0.0.1:8000 --headless -u 50 -r 5 -t 3m --html pruebas/reporte_carga.html

    -u 50  -> 50 usuarios simultáneos     -r 5  -> se suman 5 usuarios por segundo
    -t 3m  -> la prueba dura 3 minutos    --html -> reporte con tablas y gráficos

Sin --headless se abre la interfaz web en http://localhost:8089 con gráficos en vivo.

Al terminar, borra las cuentas de prueba:
    python manage.py shell -c "from django.contrib.auth.models import User; print(User.objects.filter(username__startswith='carga_').delete())"
"""
import uuid

from locust import HttpUser, between, events, task

META_P95_MS = 3000  # percentil 95: el 95 % de las respuestas debe tardar menos que esto
MAX_ERRORES = 0.01  # se tolera hasta 1 % de peticiones con error


class Cliente(HttpUser):
    wait_time = between(1, 3)  # segundos que "piensa" un usuario entre una página y otra

    def on_start(self):
        """Se ejecuta una vez por usuario simulado: crea su cuenta e inicia sesión."""
        email = f"carga_{uuid.uuid4().hex[:10]}@carga.invalid"
        clave = "ClaveCarga123"

        self.client.get("/register/", name="/register/ [GET]")
        self.client.post("/register/", {
            "first_name": "Usuario", "last_name": "Carga", "email": email, "password": clave,
            "csrfmiddlewaretoken": self.csrf(),
        }, name="/register/ [POST]")

        self.client.get("/login/", name="/login/ [GET]")
        with self.client.post("/login/", {
            "email": email, "password": clave, "csrfmiddlewaretoken": self.csrf(),
        }, name="/login/ [POST]", catch_response=True) as respuesta:
            # Si el login falla, la vista redirige de vuelta a /login/
            if respuesta.url and respuesta.url.rstrip("/").endswith("/login"):
                respuesta.failure("No se pudo iniciar sesión")

    def csrf(self):
        """Django protege los formularios con un token CSRF que viene en una cookie."""
        return self.client.cookies.get("csrftoken", "")

    @task(3)
    def inicio(self):
        self.client.get("/")

    @task(3)
    def lista_precios(self):
        self.client.get("/lista_precios/")

    @task(2)
    def formulario_reservas(self):
        self.client.get("/reservas/")

    @task(2)
    def mis_reservas(self):
        self.client.get("/mis-reservas/")


@events.quitting.add_listener
def evaluar_meta(environment, **kwargs):
    """Al terminar, decide si CP-16 aprueba y lo deja en el código de salida (0 = aprobó)."""
    total = environment.stats.total
    p95 = total.get_response_time_percentile(0.95)
    print(f"\nCP-16 -> peticiones: {total.num_requests}, errores: {total.fail_ratio:.1%}, "
          f"p95: {p95} ms (meta < {META_P95_MS} ms), promedio: {total.avg_response_time:.0f} ms")
    if total.fail_ratio > MAX_ERRORES or p95 >= META_P95_MS:
        print("CP-16 NO APROBADO")
        environment.process_exit_code = 1
    else:
        print("CP-16 APROBADO")
        environment.process_exit_code = 0
