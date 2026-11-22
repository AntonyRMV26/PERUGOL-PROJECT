const formulario = document.querySelector("#reserva-form");
const campos = ["cancha", "fecha", "inicio", "fin"].map((nombre) => formulario.elements[nombre]);
const estado = document.querySelector("#estado-disponibilidad");
const mensaje = document.querySelector("#mensaje-disponibilidad");
const alternativas = document.querySelector("#alternativas-disponibilidad");
const opciones = document.querySelector("#opciones-disponibilidad");
let consulta;

function mostrar(etiqueta, texto, alerta = false, rangos = []) {
  estado.textContent = etiqueta;
  estado.classList.toggle("chip-amber", alerta);
  mensaje.textContent = texto;
  opciones.replaceChildren();
  for (const [inicio, fin] of rangos) {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "btn btn-outline-verde";
    boton.dataset.inicio = inicio;
    boton.dataset.fin = fin;
    boton.textContent = inicio + "–" + fin;
    opciones.append(boton);
  }
  alternativas.hidden = !rangos.length;
}

async function comprobar() {
  consulta?.abort();
  if (campos.some((campo) => !campo.value)) {
    mostrar("Por comprobar", "Selecciona cancha, fecha y horas para consultar disponibilidad.");
    return;
  }

  const actual = new AbortController();
  consulta = actual;
  const parametros = new URLSearchParams(campos.map((campo) => [campo.name, campo.value]));
  mostrar("Comprobando…", "Consultando la agenda.");
  try {
    const respuesta = await fetch(formulario.dataset.disponibilidad + "?" + parametros, { signal: actual.signal });
    if (!respuesta.ok && respuesta.status !== 400) throw new Error("Consulta no disponible");
    const datos = await respuesta.json();
    if (actual.signal.aborted) return;
    mostrar(datos.disponible ? "Disponible" : "Revisa el horario", datos.mensaje, !datos.disponible, datos.alternativas);
  } catch {
    if (actual.signal.aborted) return;
    mostrar("Por comprobar", "No se pudo consultar la agenda. El servidor validará el horario al guardar.", true);
  }
}

for (const campo of campos) campo.addEventListener("change", comprobar);

opciones.addEventListener("click", (evento) => {
  const boton = evento.target.closest("[data-inicio][data-fin]");
  if (!boton) return;
  formulario.elements.inicio.value = boton.dataset.inicio;
  formulario.elements.fin.value = boton.dataset.fin;
  formulario.elements.inicio.focus();
  comprobar();
});

if (!formulario.querySelector(".errorlist")) comprobar();
