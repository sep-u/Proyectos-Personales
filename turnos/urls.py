from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('reservas/', views.reservas, name='reservas'),
    path('lista_precios/', views.lista_precios, name='lista_precios'),
    path('register/', views.register, name='register'),
    path('login/', views.login_user, name='login'),
    path('logout/', views.logout_user, name='logout'),
    path('mis-reservas/', views.mis_reservas, name='mis_reservas'),
    path('cancelar-reserva/<int:reserva_id>/', views.cancelar_reserva, name='cancelar_reserva'),

    # Nueva ruta para el admin
    path('admin-horarios/generar/', views.generar_horarios, name='generar_horarios'),
    path('staff/dashboard/', views.dashboard_staff, name='dashboard_staff'),
]
