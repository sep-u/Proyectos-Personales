import threading
from datetime import time, timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import EstadoReserva, HorarioDisponible, PrecioServicio, Reserva, Servicio


class PanelTestBase(TestCase):
    """Datos comunes: un staff, un cliente, un servicio y horarios hoy/mañana."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.manana = self.hoy + timedelta(days=1)
        self.staff = User.objects.create_user("staff@test.cl", password="clave123", is_staff=True)
        self.cliente = User.objects.create_user("cliente@test.cl", password="clave123")
        self.servicio = Servicio.objects.create(nombre="Lavado")
        PrecioServicio.objects.create(servicio=self.servicio, tamano_vehiculo="unico", precio=10000)
        self.h_hoy = HorarioDisponible.objects.create(fecha=self.hoy, hora=time(10))
        self.h_manana = HorarioDisponible.objects.create(fecha=self.manana, hora=time(10))
        self.h_libre = HorarioDisponible.objects.create(fecha=self.manana, hora=time(11))
        self.client.force_login(self.staff)

    def crear_reserva(self, horario):
        return Reserva.objects.create(
            usuario=self.cliente, horario=horario, nombre="Ana", email="ana@test.cl",
            telefono="123", servicio=self.servicio, tamano_vehiculo="unico", precio=10000,
        )


class AccesoPanelTests(PanelTestBase):
    def test_todas_las_paginas_cargan_para_staff(self):
        r = self.crear_reserva(self.h_hoy)
        urls = [
            reverse("panel_agenda"), reverse("panel_reservas"),
            reverse("panel_reservas") + "?vista=todas&q=ana",
            reverse("panel_reserva", args=[r.id]), reverse("generar_horarios"),
            reverse("panel_servicios"), reverse("panel_servicio_nuevo"),
            reverse("panel_servicio", args=[self.servicio.id]), reverse("dashboard_staff"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_cliente_normal_no_entra(self):
        self.client.force_login(self.cliente)
        respuesta = self.client.get(reverse("panel_agenda"))
        self.assertEqual(respuesta.status_code, 302)  # redirige al login

    def test_acciones_solo_por_post(self):
        r = self.crear_reserva(self.h_hoy)
        respuesta = self.client.get(reverse("panel_cambiar_estado"), {"ids": r.id, "estado": "cancelada"})
        self.assertEqual(respuesta.status_code, 405)


class EstadoReservaTests(PanelTestBase):
    def cambiar(self, reserva, estado):
        self.client.post(reverse("panel_cambiar_estado"), {"ids": [reserva.id], "estado": estado})
        reserva.refresh_from_db()

    def test_completar_reserva_de_hoy(self):
        r = self.crear_reserva(self.h_hoy)
        self.cambiar(r, EstadoReserva.COMPLETADA)
        self.assertEqual(r.estado, EstadoReserva.COMPLETADA)

    def test_no_se_completa_un_turno_futuro(self):
        r = self.crear_reserva(self.h_manana)
        self.cambiar(r, EstadoReserva.COMPLETADA)
        self.assertEqual(r.estado, EstadoReserva.PENDIENTE)

    def test_cancelar_libera_el_horario_y_no_se_reactiva(self):
        r = self.crear_reserva(self.h_manana)
        self.cambiar(r, EstadoReserva.CANCELADA)
        self.h_manana.refresh_from_db()
        self.assertTrue(self.h_manana.disponible)
        self.cambiar(r, EstadoReserva.PENDIENTE)
        self.assertEqual(r.estado, EstadoReserva.CANCELADA)

    def test_next_externo_no_redirige_fuera_del_sitio(self):
        r = self.crear_reserva(self.h_hoy)
        respuesta = self.client.post(reverse("panel_cambiar_estado"),
                                     {"ids": [r.id], "estado": "completada", "next": "https://malo.com/"})
        self.assertEqual(respuesta.url, reverse("panel_reservas"))


class ReprogramarTests(PanelTestBase):
    def test_mover_a_horario_libre(self):
        r = self.crear_reserva(self.h_manana)
        self.client.post(reverse("panel_reprogramar", args=[r.id]), {"horario": self.h_libre.id})
        r.refresh_from_db()
        self.h_manana.refresh_from_db()
        self.h_libre.refresh_from_db()
        self.assertEqual(r.horario, self.h_libre)
        self.assertTrue(self.h_manana.disponible)   # el anterior quedó libre
        self.assertFalse(self.h_libre.disponible)   # el nuevo quedó tomado

    def test_no_mover_a_horario_ocupado(self):
        r = self.crear_reserva(self.h_manana)
        self.crear_reserva(self.h_libre)  # otra persona ya lo tomó
        self.client.post(reverse("panel_reprogramar", args=[r.id]), {"horario": self.h_libre.id})
        r.refresh_from_db()
        self.assertEqual(r.horario, self.h_manana)


class HorariosTests(PanelTestBase):
    def test_cerrar_dia_conserva_horarios_con_reserva(self):
        self.crear_reserva(self.h_manana)
        fecha = self.manana.isoformat()
        self.client.post(reverse("panel_eliminar_libres"), {"fecha_inicio": fecha, "fecha_fin": fecha})
        self.assertTrue(HorarioDisponible.objects.filter(id=self.h_manana.id).exists())
        self.assertFalse(HorarioDisponible.objects.filter(id=self.h_libre.id).exists())

    def test_reservas_publicas_no_muestran_fechas_pasadas(self):
        ayer = HorarioDisponible.objects.create(fecha=self.hoy - timedelta(days=1), hora=time(9))
        self.crear_reserva(ayer).cancelar()  # queda "disponible" pero ya pasó
        respuesta = self.client.get(reverse("reservas"))
        self.assertNotIn(ayer, respuesta.context["horarios_disponibles"])


class ServiciosTests(PanelTestBase):
    def test_crear_servicio_con_precios(self):
        datos = {
            "nombre": "Encerado", "descripcion": "", "orden": 1, "activo": "on",
            "precios-TOTAL_FORMS": 2, "precios-INITIAL_FORMS": 0,
            "precios-0-tamano_vehiculo": "pequeno", "precios-0-precio": 8000,
            "precios-1-tamano_vehiculo": "grande", "precios-1-precio": 12000,
        }
        respuesta = self.client.post(reverse("panel_servicio_nuevo"), datos)
        self.assertRedirects(respuesta, reverse("panel_servicios"))
        servicio = Servicio.objects.get(nombre="Encerado")
        self.assertEqual(servicio.precios.count(), 2)


class ModificarReservaClienteTests(PanelTestBase):
    """El cliente modifica/cancela su reserva solo con 12 h de anticipación."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.cliente)
        lejos = timezone.localtime() + timedelta(days=2)
        self.h_lejos = HorarioDisponible.objects.create(fecha=lejos.date(), hora=time(10))
        self.h_otro = HorarioDisponible.objects.create(fecha=lejos.date(), hora=time(12))

    def horario_en(self, horas):
        momento = timezone.localtime() + timedelta(hours=horas)
        return HorarioDisponible.objects.create(fecha=momento.date(), hora=momento.time().replace(microsecond=0))

    def test_modificar_con_anticipacion(self):
        r = self.crear_reserva(self.h_lejos)
        self.client.post(reverse("modificar_reserva", args=[r.id]), {"horario": self.h_otro.id})
        r.refresh_from_db()
        self.h_lejos.refresh_from_db()
        self.assertEqual(r.horario, self.h_otro)
        self.assertTrue(self.h_lejos.disponible)

    def test_no_modificar_con_menos_de_12_horas(self):
        r = self.crear_reserva(self.horario_en(5))
        self.client.post(reverse("modificar_reserva", args=[r.id]), {"horario": self.h_otro.id})
        r.refresh_from_db()
        self.assertNotEqual(r.horario, self.h_otro)
        self.assertFalse(r.se_puede_cancelar)

    def test_si_se_puede_con_mas_de_12_horas(self):
        r = self.crear_reserva(self.horario_en(13))
        self.assertTrue(r.se_puede_modificar)

    def test_no_modificar_reserva_ajena(self):
        otro = User.objects.create_user("otro@test.cl", password="clave123")
        r = self.crear_reserva(self.h_lejos)
        self.client.force_login(otro)
        respuesta = self.client.get(reverse("modificar_reserva", args=[r.id]))
        self.assertEqual(respuesta.status_code, 404)

    def test_pagina_carga_y_no_ofrece_horas_pasadas(self):
        r = self.crear_reserva(self.h_lejos)
        pasado = self.horario_en(-2)
        respuesta = self.client.get(reverse("modificar_reserva", args=[r.id]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn(pasado, respuesta.context["horarios"])


class ExportarDashboardTests(PanelTestBase):
    def test_descarga_excel_con_datos_del_periodo(self):
        from io import BytesIO
        from openpyxl import load_workbook

        r = self.crear_reserva(self.h_hoy)
        r.cambiar_estado(EstadoReserva.COMPLETADA)
        respuesta = self.client.get(reverse("dashboard_exportar"), {"periodo": 7})

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("attachment", respuesta["Content-Disposition"])
        self.assertIn(".xlsx", respuesta["Content-Disposition"])

        wb = load_workbook(BytesIO(respuesta.content))
        self.assertIn("Resumen", wb.sheetnames)
        self.assertIn("Reservas", wb.sheetnames)
        hoja = wb["Reservas"]
        self.assertEqual(hoja.max_row, 2)  # encabezado + 1 reserva
        self.assertEqual(hoja["C2"].value, "Ana")
        self.assertEqual(hoja["J2"].value, 10000)

    def test_cliente_normal_no_puede_descargar(self):
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(reverse("dashboard_exportar")).status_code, 302)

    def test_periodo_invalido_usa_30_dias(self):
        respuesta = self.client.get(reverse("dashboard_exportar"), {"periodo": "abc"})
        self.assertEqual(respuesta.status_code, 200)


class ReservarTests(PanelTestBase):
    """Flujo principal del cliente: reservar un horario desde /reservas/."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.cliente)
        self.precio = PrecioServicio.objects.get(servicio=self.servicio)

    def datos(self, **cambios):
        datos = {
            "nombre": "Ana", "email": "ana@test.cl", "telefono": "912345678",
            "precio_servicio": self.precio.id, "horario": self.h_libre.id,
            "marca_modelo_auto": "Toyota Yaris",
        }
        datos.update(cambios)
        return datos

    def test_pagina_carga(self):
        self.assertEqual(self.client.get(reverse("reservas")).status_code, 200)

    def test_reservar_ocupa_el_horario_y_envia_correo(self):
        from django.core import mail

        respuesta = self.client.post(reverse("reservas"), self.datos())
        self.assertRedirects(respuesta, reverse("mis_reservas"))
        reserva = Reserva.objects.get()
        self.assertEqual(reserva.usuario, self.cliente)
        self.assertEqual(reserva.precio, 10000)  # el precio se copia del servicio
        self.h_libre.refresh_from_db()
        self.assertFalse(self.h_libre.disponible)
        self.assertEqual(len(mail.outbox), 1)  # en tests Django guarda los correos en memoria

    def test_campos_vacios_no_crean_reserva(self):
        self.client.post(reverse("reservas"), self.datos(nombre="", telefono=""))
        self.assertFalse(Reserva.objects.exists())

    def test_horario_ocupado_da_404(self):
        self.crear_reserva(self.h_libre)
        respuesta = self.client.post(reverse("reservas"), self.datos())
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(Reserva.objects.count(), 1)

    def test_servicio_inactivo_da_404(self):
        self.servicio.activo = False
        self.servicio.save()
        respuesta = self.client.post(reverse("reservas"), self.datos())
        self.assertEqual(respuesta.status_code, 404)

    def test_sin_sesion_redirige_al_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse("reservas"))
        self.assertEqual(respuesta.status_code, 302)


class CancelarReservaClienteTests(PanelTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.cliente)

    def test_cancelar_con_anticipacion_libera_horario(self):
        lejos = timezone.localdate() + timedelta(days=3)
        horario = HorarioDisponible.objects.create(fecha=lejos, hora=time(10))
        r = self.crear_reserva(horario)
        self.client.post(reverse("cancelar_reserva", args=[r.id]))
        r.refresh_from_db()
        horario.refresh_from_db()
        self.assertEqual(r.estado, EstadoReserva.CANCELADA)
        self.assertTrue(horario.disponible)

    def test_no_cancelar_con_menos_de_12_horas(self):
        momento = timezone.localtime() + timedelta(hours=5)
        horario = HorarioDisponible.objects.create(fecha=momento.date(), hora=momento.time().replace(microsecond=0))
        r = self.crear_reserva(horario)
        self.client.post(reverse("cancelar_reserva", args=[r.id]))
        r.refresh_from_db()
        self.assertEqual(r.estado, EstadoReserva.PENDIENTE)

    def test_no_cancelar_reserva_ajena(self):
        r = self.crear_reserva(self.h_manana)
        otro = User.objects.create_user("otro@test.cl", password="clave123")
        self.client.force_login(otro)
        respuesta = self.client.post(reverse("cancelar_reserva", args=[r.id]))
        self.assertEqual(respuesta.status_code, 404)

    def test_mis_reservas_muestra_solo_las_propias(self):
        mia = self.crear_reserva(self.h_manana)
        otro = User.objects.create_user("otro@test.cl", password="clave123")
        Reserva.objects.create(usuario=otro, horario=self.h_libre, nombre="Otro", email="o@test.cl",
                               telefono="1", servicio=self.servicio, tamano_vehiculo="unico", precio=1)
        respuesta = self.client.get(reverse("mis_reservas"))
        self.assertEqual(list(respuesta.context["reservas"]), [mia])


class CuentasTests(TestCase):
    """Registro, inicio y cierre de sesión (el email se usa como username)."""

    def registrar(self, **cambios):
        datos = {"first_name": "Ana", "last_name": "Pérez", "email": "ana@test.cl", "password": "clave123"}
        datos.update(cambios)
        return self.client.post(reverse("register"), datos)

    def test_paginas_publicas_cargan(self):
        for nombre in ("home", "lista_precios", "register", "login"):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)

    def test_registro_crea_usuario_con_email_como_username(self):
        respuesta = self.registrar()
        self.assertRedirects(respuesta, reverse("login"))
        usuario = User.objects.get(username="ana@test.cl")
        self.assertTrue(usuario.check_password("clave123"))  # se guarda cifrada, no en texto plano
        self.assertFalse(usuario.is_staff)

    def test_registro_con_email_repetido_no_duplica(self):
        self.registrar()
        respuesta = self.registrar(first_name="Otra")
        self.assertRedirects(respuesta, reverse("register"))
        self.assertEqual(User.objects.count(), 1)

    def test_registro_con_clave_corta_muestra_error(self):
        respuesta = self.registrar(password="123")
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_login_correcto(self):
        User.objects.create_user("ana@test.cl", password="clave123")
        respuesta = self.client.post(reverse("login"), {"email": "ana@test.cl", "password": "clave123"})
        self.assertRedirects(respuesta, reverse("home"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_con_clave_incorrecta(self):
        User.objects.create_user("ana@test.cl", password="clave123")
        respuesta = self.client.post(reverse("login"), {"email": "ana@test.cl", "password": "mala"})
        self.assertRedirects(respuesta, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout(self):
        usuario = User.objects.create_user("ana@test.cl", password="clave123")
        self.client.force_login(usuario)
        self.client.get(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class DatosDemoTests(TestCase):
    def setUp(self):
        servicio = Servicio.objects.create(nombre="Lavado demo test")
        PrecioServicio.objects.create(servicio=servicio, tamano_vehiculo="unico", precio=10000)

    def ejecutar(self, *args):
        from io import StringIO
        from django.core.management import call_command
        call_command("datos_demo", *args, stdout=StringIO())

    def test_cargar_y_borrar(self):
        self.ejecutar("--dias", "5", "--futuro", "3")
        demo = Reserva.objects.filter(usuario__username__startswith="demo_")
        self.assertTrue(demo.exists())
        self.assertTrue(demo.filter(horario__fecha__gte=timezone.localdate()).exists())

        self.ejecutar("--borrar")
        self.assertFalse(User.objects.filter(username__startswith="demo_").exists())
        self.assertFalse(Reserva.objects.exists())
        # Los horarios futuros quedan libres para clientes reales
        self.assertFalse(HorarioDisponible.objects.filter(fecha__gte=timezone.localdate(), disponible=False).exists())

    def test_no_carga_dos_veces(self):
        from django.core.management.base import CommandError
        self.ejecutar("--dias", "2")
        with self.assertRaises(CommandError):
            self.ejecutar("--dias", "2")


class ConcurrenciaReservaTests(TransactionTestCase):
    """CP-06: dos clientes reservan el mismo horario exactamente al mismo tiempo.

    Usa TransactionTestCase (y no TestCase) porque cada hilo abre su propia conexión
    a la base de datos y necesita ver los datos ya confirmados (commit). TestCase
    envuelve todo en una transacción que los otros hilos no pueden ver.
    """

    def setUp(self):
        servicio = Servicio.objects.create(nombre="Lavado CP-06")
        self.precio = PrecioServicio.objects.create(servicio=servicio, tamano_vehiculo="unico", precio=10000)
        manana = timezone.localdate() + timedelta(days=1)
        self.horario = HorarioDisponible.objects.create(fecha=manana, hora=time(10))
        self.clientes = []
        for i in range(2):
            usuario = User.objects.create_user(f"cliente{i}@test.cl", password="clave123")
            navegador = Client()  # un "navegador" independiente por cliente
            navegador.force_login(usuario)
            self.clientes.append(navegador)

    def test_solo_una_reserva_queda_registrada(self):
        barrera = threading.Barrier(len(self.clientes))  # hace que ambos hilos partan a la vez
        datos = {
            "nombre": "Cliente", "email": "c@test.cl", "telefono": "912345678",
            "precio_servicio": self.precio.id, "horario": self.horario.id, "marca_modelo_auto": "Kia Rio",
        }

        def reservar(navegador):
            try:
                barrera.wait()
                navegador.post(reverse("reservas"), datos)
            finally:
                connection.close()  # cada hilo cierra su conexión, si no la BD de test queda "en uso"

        hilos = [threading.Thread(target=reservar, args=(n,)) for n in self.clientes]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(Reserva.objects.filter(horario=self.horario).count(), 1)
