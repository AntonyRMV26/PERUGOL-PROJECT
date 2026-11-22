for (const fila of document.querySelectorAll("[data-horario]")) {
  const control = fila.querySelector("input[type=checkbox]");
  const estado = fila.querySelector("[data-estado]");
  const horas = fila.querySelectorAll("input[type=time]");
  const actualizar = () => {
    estado.textContent = control.checked ? "Habilitado" : "Cerrado";
    estado.classList.toggle("chip-amber", !control.checked);
    for (const hora of horas) {
      hora.disabled = !control.checked;
      hora.required = control.checked;
    }
  };
  control.addEventListener("change", actualizar);
  actualizar();
}
