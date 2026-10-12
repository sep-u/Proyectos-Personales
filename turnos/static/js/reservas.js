document.addEventListener('click', function (e) {
  if (!e.target || e.target.id !== 'nextBtn') {
    return;
  }

  const step1 = document.getElementById('step1');
  const step2 = document.getElementById('step2');
  const horarioSelect = document.getElementById('horario');
  const formHorario = document.getElementById('formHorario');

  if (!horarioSelect || !horarioSelect.value) {
    alert('Por favor selecciona un horario antes de continuar.');
    return;
  }

  formHorario.value = horarioSelect.value;
  step1.style.display = 'none';
  step2.style.display = 'block';
});
