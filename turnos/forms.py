from django import forms
from django.contrib.auth.models import User
from datetime import datetime, timedelta

class RegistroForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, min_length=5)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password']
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido',
        }


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)


class DiasSemanaWidget(forms.CheckboxSelectMultiple):
    """CheckboxSelectMultiple que deja el domingo deshabilitado (no se trabaja ese día)."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if str(value) == '6':  # 6 = Domingo
            option['attrs']['disabled'] = True
        return option


class GenerarHorariosForm(forms.Form):
    fecha_inicio = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'text', 'class': 'form-control flatpickr-fecha'}),
        label="Fecha inicio"
    )
    fecha_fin = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'text', 'class': 'form-control flatpickr-fecha'}),
        label="Fecha fin"
    )
    hora_inicio = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        label="Hora de inicio"
    )
    hora_fin = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        label="Hora de término"
    )
    intervalo_minutos = forms.IntegerField(
        min_value=5, initial=30,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        label="Intervalo (minutos)"
    )
    dias_semana = forms.MultipleChoiceField(
        choices=[
            (0, 'Lunes'), (1, 'Martes'), (2, 'Miércoles'), (3, 'Jueves'),
            (4, 'Viernes'), (5, 'Sábado'), (6, 'Domingo (cerrado)'),
        ],
        widget=DiasSemanaWidget,
        label="Días de la semana a incluir",
        required=True,
    )


    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        hora_inicio = cleaned_data.get('hora_inicio')
        hora_fin = cleaned_data.get('hora_fin')

        if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
            raise forms.ValidationError("La fecha de inicio no puede ser posterior a la fecha de fin.")

        if hora_inicio and hora_fin and hora_inicio >= hora_fin:
            raise forms.ValidationError("La hora de inicio debe ser menor a la hora de término.")

        dias_semana = cleaned_data.get('dias_semana')
        if dias_semana:
            cleaned_data['dias_semana'] = [d for d in dias_semana if d != '6']

        return cleaned_data