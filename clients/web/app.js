const estado = document.querySelector("#estado");
const estadoTexto = document.querySelector("#estado-texto");
const mensajes = document.querySelector("#mensajes");
const bienvenida = document.querySelector("#bienvenida");
const formulario = document.querySelector("#formulario");
const entrada = document.querySelector("#entrada");
const enviar = document.querySelector("#enviar");
const uso = document.querySelector("#uso");
const instalar = document.querySelector("#instalar");
const modal = document.querySelector("#modal");
const cerrarModal = document.querySelector("#cerrar-modal");
const abrirEstado = document.querySelector("#abrir-estado");
const panelEstado = document.querySelector("#panel-estado");
const cerrarEstado = document.querySelector("#cerrar-estado");
const estadoNucleo = document.querySelector("#estado-nucleo");
const estadoProveedor = document.querySelector("#estado-proveedor");
const estadoModelo = document.querySelector("#estado-modelo");
const estadoTiempo = document.querySelector("#estado-tiempo");
const estadoConexiones = document.querySelector("#estado-conexiones");
const estadoEnrutador = document.querySelector("#estado-enrutador");
const formularioIA = document.querySelector("#formulario-ia");
const iaPrincipal = document.querySelector("#ia-principal");
const iaModeloPrincipal = document.querySelector("#ia-modelo-principal");
const iaRespaldo = document.querySelector("#ia-respaldo");
const iaModeloRespaldo = document.querySelector("#ia-modelo-respaldo");
const iaAutomatico = document.querySelector("#ia-automatico");
const iaReintento = document.querySelector("#ia-reintento");
const guardarIA = document.querySelector("#guardar-ia");
const resultadoIA = document.querySelector("#resultado-ia");
const estadoNotificaciones = document.querySelector("#estado-notificaciones");
const activarPush = document.querySelector("#activar-push");
const probarPush = document.querySelector("#probar-push");
const desactivarPush = document.querySelector("#desactivar-push");
let socket = null;
let respuestaActual = null;
let respondiendo = false;
let reintento = null;
let esperaReconexion = 1000;
let huboConexion = false;
let clavePublicaPush = null;
let peticionesSesion = 0;
let tokensSesion = 0;
let costeSesion = 0;
let csrfIA = null;
let proveedoresIA = {};
let turnoSiguiente = 0;
let turnoRespuesta = null;
let sesionVisual = 0;
let editorAbierto = null;

function mostrarEstado(tipo, texto) { estado.className = `estado ${tipo}`; estadoTexto.textContent = texto; }
function desplazar() { mensajes.scrollTo({ top: mensajes.scrollHeight, behavior: "smooth" }); }
function ocultarBienvenida() { if (bienvenida) bienvenida.hidden = true; }
function reiniciarUsoSesion() {
  peticionesSesion = 0;
  tokensSesion = 0;
  costeSesion = 0;
  uso.textContent = "";
  uso.hidden = true;
}
function agregarMensaje(texto, autor, turno = null) {
  ocultarBienvenida();
  const contenedor = document.createElement("article"); contenedor.className = `mensaje ${autor}`;
  if (Number.isInteger(turno)) contenedor.dataset.turn = String(turno);
  contenedor.dataset.session = String(sesionVisual);
  const burbuja = document.createElement("div"); burbuja.className = "burbuja";
  const cabeceraMensaje = document.createElement("div"); cabeceraMensaje.className = "cabecera-mensaje";
  const etiqueta = document.createElement("span"); etiqueta.className = "autor"; etiqueta.textContent = autor === "jhony" ? "Jhony" : "ASTRO";
  cabeceraMensaje.appendChild(etiqueta);
  if (autor === "jhony" && Number.isInteger(turno)) {
    contenedor.dataset.confirmed = "false";
    const editar = document.createElement("button"); editar.className = "editar-mensaje"; editar.type = "button";
    editar.textContent = "Editar"; editar.setAttribute("aria-label", "Editar mensaje"); editar.disabled = true;
    cabeceraMensaje.appendChild(editar);
  }
  const contenido = document.createElement("p"); contenido.className = "texto"; contenido.textContent = texto;
  burbuja.append(cabeceraMensaje, contenido); contenedor.appendChild(burbuja); mensajes.appendChild(contenedor); desplazar(); return contenido;
}
function agregarSistema(texto) { ocultarBienvenida(); const elemento = document.createElement("p"); elemento.className = "sistema"; elemento.textContent = texto; mensajes.appendChild(elemento); desplazar(); }
function ajustarEntrada() { entrada.style.height = "auto"; entrada.style.height = `${Math.min(entrada.scrollHeight, 132)}px`; }
function habilitarEntrada() {
  const conectado = socket && socket.readyState === WebSocket.OPEN;
  entrada.disabled = !conectado || respondiendo; enviar.disabled = !conectado || respondiendo || !entrada.value.trim();
  document.querySelectorAll(".editar-mensaje").forEach((boton) => {
    const mensaje = boton.closest(".mensaje");
    boton.disabled = !conectado || respondiendo || Boolean(editorAbierto)
      || mensaje.dataset.session !== String(sesionVisual)
      || mensaje.dataset.confirmed !== "true";
  });
}
function cancelarEdicion() {
  if (!editorAbierto) return;
  const { contenido, boton, formularioEdicion } = editorAbierto;
  formularioEdicion.remove(); contenido.hidden = false; boton.hidden = false; editorAbierto = null; habilitarEntrada();
}
function iniciarEdicion(contenedor) {
  const conectado = socket && socket.readyState === WebSocket.OPEN;
  if (!conectado || respondiendo || editorAbierto || contenedor.dataset.session !== String(sesionVisual) || contenedor.dataset.confirmed !== "true") return;
  const contenido = contenedor.querySelector(".texto");
  const boton = contenedor.querySelector(".editar-mensaje");
  const formularioEdicion = document.createElement("form"); formularioEdicion.className = "formulario-edicion";
  const campo = document.createElement("textarea"); campo.value = contenido.textContent; campo.maxLength = 4000; campo.rows = 3;
  campo.setAttribute("aria-label", "Corregir mensaje");
  const aviso = document.createElement("p"); aviso.textContent = "La respuesta y los mensajes posteriores se reemplazarán.";
  const acciones = document.createElement("div"); acciones.className = "acciones-edicion";
  const cancelar = document.createElement("button"); cancelar.type = "button"; cancelar.className = "cancelar-edicion"; cancelar.textContent = "Cancelar";
  const guardar = document.createElement("button"); guardar.type = "submit"; guardar.className = "guardar-edicion"; guardar.textContent = "Guardar y rehacer";
  acciones.append(cancelar, guardar); formularioEdicion.append(campo, aviso, acciones);
  contenido.hidden = true; boton.hidden = true; contenedor.querySelector(".burbuja").appendChild(formularioEdicion);
  editorAbierto = { contenedor, contenido, boton, formularioEdicion, campo, guardar, cancelar };
  cancelar.addEventListener("click", cancelarEdicion);
  formularioEdicion.addEventListener("submit", (evento) => {
    evento.preventDefault(); const texto = campo.value.trim();
    if (!texto) { campo.focus(); return; }
    if (texto === contenido.textContent) { cancelarEdicion(); return; }
    respondiendo = true; campo.disabled = true; guardar.disabled = true; cancelar.disabled = true; guardar.textContent = "Corrigiendo…";
    turnoRespuesta = Number(contenedor.dataset.turn); uso.hidden = true; habilitarEntrada();
    socket.send(JSON.stringify({ type: "edit", turn: turnoRespuesta, text: texto }));
  });
  habilitarEntrada(); campo.focus(); campo.setSelectionRange(campo.value.length, campo.value.length);
}
function aplicarRebobinado(turno, texto) {
  const objetivo = [...mensajes.querySelectorAll(".mensaje.jhony")].find((mensaje) =>
    mensaje.dataset.session === String(sesionVisual) && Number(mensaje.dataset.turn) === turno
  );
  if (!objetivo) { cancelarEdicion(); agregarSistema("No pude localizar el mensaje que se corrigió."); return; }
  let elemento = objetivo;
  while (elemento) { const siguiente = elemento.nextSibling; elemento.remove(); elemento = siguiente; }
  editorAbierto = null; turnoSiguiente = turno + 1; turnoRespuesta = turno;
  agregarMensaje(texto, "jhony", turno); habilitarEntrada();
}
async function pedirJSON(url, opciones = {}) {
  const respuesta = await fetch(url, opciones);
  const datos = await respuesta.json();
  if (!respuesta.ok) throw new Error(datos.detail || "La operación no pudo completarse.");
  return datos;
}
function formatearTiempo(segundos) {
  if (segundos < 60) return `${segundos} s`;
  if (segundos < 3600) return `${Math.floor(segundos / 60)} min`;
  return `${Math.floor(segundos / 3600)} h ${Math.floor((segundos % 3600) / 60)} min`;
}
function base64ABytes(base64) {
  const relleno = "=".repeat((4 - base64.length % 4) % 4);
  const normalizado = (base64 + relleno).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(normalizado), (caracter) => caracter.charCodeAt(0));
}
async function actualizarPanel() {
  try {
    const datos = await pedirJSON("/status");
    estadoNucleo.textContent = datos.status === "ok" ? "En línea" : "Con problemas";
    estadoProveedor.textContent = datos.provider;
    estadoModelo.textContent = datos.model;
    estadoTiempo.textContent = formatearTiempo(datos.uptime_seconds);
    estadoConexiones.textContent = String(datos.websocket_connections);
    estadoEnrutador.textContent = datos.ai.degraded
      ? `Modo respaldo. Se volverá a probar el principal en ${datos.ai.retry_in_seconds} s.`
      : "Proveedor principal activo.";
  } catch {
    estadoNucleo.textContent = "No disponible";
  }
  await cargarAjustesIA();
  await actualizarEstadoPush();
}
function llenarProveedor(select, proveedores, elegido) {
  select.replaceChildren(...proveedores.map((proveedor) => {
    const opcion = document.createElement("option");
    opcion.value = proveedor.id; opcion.textContent = proveedor.name; return opcion;
  }));
  select.value = elegido;
}
function sincronizarModelos() {
  iaModeloPrincipal.value = proveedoresIA[iaPrincipal.value]?.model || "";
  iaModeloRespaldo.value = proveedoresIA[iaRespaldo.value]?.model || "";
}
async function cargarAjustesIA() {
  try {
    const datos = await pedirJSON("/ai/settings");
    csrfIA = datos.csrf_token;
    proveedoresIA = Object.fromEntries(datos.providers.map((item) => [item.id, item]));
    llenarProveedor(iaPrincipal, datos.providers, datos.primary);
    llenarProveedor(iaRespaldo, datos.providers, datos.fallback);
    iaAutomatico.checked = datos.automatic;
    iaReintento.value = String(datos.retry_seconds);
    sincronizarModelos();
    resultadoIA.textContent = "";
  } catch (error) {
    resultadoIA.textContent = error.message;
  }
}
async function actualizarEstadoPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    estadoNotificaciones.textContent = "Este dispositivo no admite Web Push.";
    activarPush.disabled = true;
    return;
  }
  const registro = await navigator.serviceWorker.ready;
  const suscripcion = await registro.pushManager.getSubscription();
  const permiso = Notification.permission;
  if (suscripcion && permiso === "granted") {
    estadoNotificaciones.textContent = "Activadas en este dispositivo.";
    activarPush.hidden = true;
    probarPush.disabled = false;
    desactivarPush.hidden = false;
  } else {
    estadoNotificaciones.textContent = permiso === "denied"
      ? "Bloqueadas en los ajustes del dispositivo."
      : "Desactivadas. Actívalas para recibir avisos con ASTRO cerrado.";
    activarPush.hidden = false;
    activarPush.disabled = permiso === "denied" || !clavePublicaPush;
    probarPush.disabled = true;
    desactivarPush.hidden = true;
  }
}
function programarReconexion() {
  if (reintento || !navigator.onLine) return;
  mostrarEstado("desconectado", "Reconectando");
  reintento = window.setTimeout(() => { reintento = null; conectar(); }, esperaReconexion);
  esperaReconexion = Math.min(esperaReconexion * 2, 10000);
}
function conectar() {
  if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) return;
  const protocolo = location.protocol === "https:" ? "wss:" : "ws:";
  mostrarEstado("conectando", "Conectando"); socket = new WebSocket(`${protocolo}//${location.host}/ws`);
  socket.addEventListener("message", ({ data }) => {
    let evento;
    try { evento = JSON.parse(data); } catch { agregarSistema("ASTRO recibió un mensaje que no pudo interpretar."); return; }
    if (evento.type === "ready") {
      mostrarEstado("conectado", "Conectado");
      if (huboConexion) {
        sesionVisual += 1; turnoSiguiente = 0; turnoRespuesta = null; cancelarEdicion();
        agregarSistema("Conexión restablecida. Comienza una sesión nueva.");
        reiniciarUsoSesion();
      }
      huboConexion = true; esperaReconexion = 1000; respondiendo = false; habilitarEntrada(); entrada.focus(); return;
    }
    if (evento.type === "rewind") { aplicarRebobinado(evento.turn, evento.text); return; }
    if (evento.type === "delta") {
      if (!respuestaActual) respuestaActual = agregarMensaje("", "astro", turnoRespuesta);
      respuestaActual.textContent += evento.text; desplazar(); return;
    }
    if (evento.type === "provider_change") {
      if (evento.reason === "proveedor principal recuperado") {
        agregarSistema(`${evento.to} volvió a estar disponible y recuperó el servicio principal.`);
      } else {
        const detalle = evento.continued_partial ? " desde el texto ya mostrado" : "";
        agregarSistema(`${evento.from} se interrumpió; continúo con ${evento.to}${detalle}.`);
      }
      estadoProveedor.textContent = evento.to; return;
    }
    if (evento.type === "done") {
      const registros = Array.isArray(evento.usage) ? evento.usage : [];
      peticionesSesion += registros.length;
      tokensSesion += registros.reduce((total, item) => total + item.tokens, 0);
      costeSesion += registros.reduce((total, item) => total + item.coste_estimado_usd, 0);
      uso.textContent = `${peticionesSesion} petición/es en esta sesión · ${tokensSesion} tokens · ${costeSesion.toFixed(6)} USD`;
      if (evento.provider && proveedoresIA[evento.provider]) {
        estadoProveedor.textContent = proveedoresIA[evento.provider].name;
      }
      if (evento.model) estadoModelo.textContent = evento.model;
      const mensajeConfirmado = [...mensajes.querySelectorAll(".mensaje.jhony")].find((mensaje) =>
        mensaje.dataset.session === String(sesionVisual) && Number(mensaje.dataset.turn) === evento.turn
      );
      if (mensajeConfirmado) mensajeConfirmado.dataset.confirmed = "true";
      turnoSiguiente = Math.max(turnoSiguiente, Number(evento.turn) + 1);
      editorAbierto = null; uso.hidden = false; respuestaActual = null; respondiendo = false; habilitarEntrada(); entrada.focus(); return;
    }
    if (evento.type === "error") {
      const eraEdicion = Boolean(editorAbierto); respondiendo = false;
      if (eraEdicion) cancelarEdicion(); else if (Number.isInteger(turnoRespuesta)) turnoSiguiente = turnoRespuesta;
      agregarSistema(`Error: ${evento.message}`); respuestaActual = null; habilitarEntrada();
    }
  });
  socket.addEventListener("close", () => {
    if (respuestaActual) agregarSistema("La respuesta se interrumpió al perder la conexión.");
    socket = null; respuestaActual = null; respondiendo = false; cancelarEdicion(); habilitarEntrada(); programarReconexion();
  });
  socket.addEventListener("error", () => mostrarEstado("desconectado", "Sin conexión"));
}
formulario.addEventListener("submit", (evento) => {
  evento.preventDefault(); const texto = entrada.value.trim();
  if (!texto || !socket || socket.readyState !== WebSocket.OPEN) return;
  turnoRespuesta = turnoSiguiente; turnoSiguiente += 1;
  agregarMensaje(texto, "jhony", turnoRespuesta); socket.send(JSON.stringify({ type: "message", text: texto }));
  entrada.value = ""; ajustarEntrada(); respuestaActual = null; respondiendo = true; uso.hidden = true; habilitarEntrada();
});
mensajes.addEventListener("click", (evento) => {
  const boton = evento.target.closest(".editar-mensaje");
  if (boton) iniciarEdicion(boton.closest(".mensaje"));
});
entrada.addEventListener("input", () => { ajustarEntrada(); habilitarEntrada(); });
entrada.addEventListener("keydown", (evento) => { if (evento.key === "Enter" && !evento.shiftKey) { evento.preventDefault(); formulario.requestSubmit(); } });
instalar.addEventListener("click", () => { modal.hidden = false; });
cerrarModal.addEventListener("click", () => { modal.hidden = true; });
modal.addEventListener("click", (evento) => { if (evento.target === modal) modal.hidden = true; });
abrirEstado.addEventListener("click", async () => {
  panelEstado.hidden = false;
  await actualizarPanel();
});
cerrarEstado.addEventListener("click", () => { panelEstado.hidden = true; });
panelEstado.addEventListener("click", (evento) => { if (evento.target === panelEstado) panelEstado.hidden = true; });
iaPrincipal.addEventListener("change", () => {
  if (iaPrincipal.value === iaRespaldo.value) {
    iaRespaldo.value = Object.keys(proveedoresIA).find((id) => id !== iaPrincipal.value) || "";
  }
  sincronizarModelos();
});
iaRespaldo.addEventListener("change", () => {
  if (iaRespaldo.value === iaPrincipal.value) {
    iaPrincipal.value = Object.keys(proveedoresIA).find((id) => id !== iaRespaldo.value) || "";
  }
  sincronizarModelos();
});
formularioIA.addEventListener("submit", async (evento) => {
  evento.preventDefault(); resultadoIA.textContent = ""; guardarIA.disabled = true;
  const modelos = Object.fromEntries(Object.entries(proveedoresIA).map(([id, item]) => [id, item.model]));
  modelos[iaPrincipal.value] = iaModeloPrincipal.value.trim();
  modelos[iaRespaldo.value] = iaModeloRespaldo.value.trim();
  try {
    const datos = await pedirJSON("/ai/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-ASTRO-CSRF": csrfIA },
      body: JSON.stringify({
        principal: iaPrincipal.value,
        respaldo: iaRespaldo.value,
        modelos,
        cambio_automatico: iaAutomatico.checked,
        reintento_principal_segundos: Number(iaReintento.value)
      })
    });
    estadoProveedor.textContent = datos.provider_name; estadoModelo.textContent = datos.model;
    estadoEnrutador.textContent = "Proveedor principal activo.";
    resultadoIA.textContent = "Configuración guardada. Se aplicará al siguiente mensaje.";
    proveedoresIA = Object.fromEntries(datos.providers.map((item) => [item.id, item]));
  } catch (error) { resultadoIA.textContent = error.message; }
  finally { guardarIA.disabled = false; }
});
activarPush.addEventListener("click", async () => {
  try {
    const permiso = await Notification.requestPermission();
    if (permiso !== "granted") { await actualizarEstadoPush(); return; }
    const registro = await navigator.serviceWorker.ready;
    const suscripcion = await registro.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64ABytes(clavePublicaPush)
    });
    await pedirJSON("/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(suscripcion)
    });
    await actualizarEstadoPush();
  } catch (error) { estadoNotificaciones.textContent = error.message; }
});
probarPush.addEventListener("click", async () => {
  probarPush.disabled = true;
  try {
    const resultado = await pedirJSON("/push/test", { method: "POST" });
    estadoNotificaciones.textContent = resultado.sent ? "Aviso de prueba enviado." : "No se pudo enviar el aviso.";
  } catch (error) { estadoNotificaciones.textContent = error.message; }
  finally { probarPush.disabled = false; }
});
desactivarPush.addEventListener("click", async () => {
  const registro = await navigator.serviceWorker.ready;
  const suscripcion = await registro.pushManager.getSubscription();
  if (suscripcion) {
    await pedirJSON("/push/unsubscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ endpoint: suscripcion.endpoint })
    });
    await suscripcion.unsubscribe();
  }
  await actualizarEstadoPush();
});
window.addEventListener("online", conectar);
window.addEventListener("offline", () => { mostrarEstado("desconectado", "Sin red"); habilitarEntrada(); });
document.addEventListener("visibilitychange", () => { if (!document.hidden) conectar(); });
if (window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone) instalar.hidden = true;
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js?v=7").catch(() => agregarSistema("La instalación sin conexión no está disponible."));
  });
}
pedirJSON("/push/public-key")
  .then((datos) => { clavePublicaPush = datos.public_key; })
  .catch(() => { clavePublicaPush = null; });
conectar();
