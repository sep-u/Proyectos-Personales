document.addEventListener('DOMContentLoaded', function () {
  const nextBtn = document.getElementById('nextBtn');
  const step1 = document.getElementById('step1');
  const step2 = document.getElementById('step2');
  const fechaInput = document.getElementById('fecha');
  const horaInput = document.getElementById('hora');
  const formFecha = document.getElementById('formFecha');
  const formHora = document.getElementById('formHora');

  nextBtn.addEventListener('click', () => {
    if (fechaInput.value && horaInput.value) {
      formFecha.value = fechaInput.value;
      formHora.value = horaInput.value;
      step1.style.display = 'none';
      step2.style.display = 'block';
    } else {
      alert('Por favor selecciona fecha y hora antes de continuar.');
    }
  });
});
