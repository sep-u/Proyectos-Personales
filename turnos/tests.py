from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
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
