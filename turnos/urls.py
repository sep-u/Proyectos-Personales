from django.urls import path
from . import views, views_panel

urlpatterns = [
    path('', views.home, name='home'),
    path('reservas/', views.reservas, name='reservas'),
    path('lista_precios/', views.lista_precios, name='lista_precios'),
    path('register/', views.register, name='register'),
    path('login/', views.login_user, name='login'),
    path('logout/', views.logout_user, name='logout'),
    path('mis-reservas/', views.mis_reservas, name='mis_reservas'),
    path('cancelar-reserva/<int:reserva_id>/', views.cancelar_reserva, name='cancelar_reserva'),
    path('modificar-reserva/<int:reserva_id>/', views.modificar_reserva, name='modificar_reserva'),

    # Panel de administración (solo staff) — ver views_panel.py
    path('panel/', views_panel.agenda, name='panel_agenda'),
    path('panel/reservas/', views_panel.reservas, name='panel_reservas'),
    path('panel/reservas/estado/', views_panel.cambiar_estado, name='panel_cambiar_estado'),
    path('panel/reservas/<int:reserva_id>/', views_panel.reserva_detalle, name='panel_reserva'),
    path('panel/reservas/<int:reserva_id>/reprogramar/', views_panel.reprogramar_reserva, name='panel_reprogramar'),
    path('panel/horarios/', views_panel.generar_horarios, name='generar_horarios'),
    path('panel/horarios/<int:horario_id>/eliminar/', views_panel.eliminar_horario, name='panel_eliminar_horario'),
    path('panel/horarios/eliminar-libres/', views_panel.eliminar_horarios_libres, name='panel_eliminar_libres'),
    path('panel/servicios/', views_panel.servicios, name='panel_servicios'),
    path('panel/servicios/nuevo/', views_panel.servicio_editar, name='panel_servicio_nuevo'),
    path('panel/servicios/<int:servicio_id>/', views_panel.servicio_editar, name='panel_servicio'),
    path('panel/servicios/<int:servicio_id>/activar/', views_panel.servicio_activar, name='panel_servicio_activar'),
    path('panel/dashboard/', views_panel.dashboard_staff, name='dashboard_staff'),
]
