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
const estadoModelo = document.querySelector("#estado-modelo");
const estadoTiempo = document.querySelector("#estado-tiempo");
const estadoConexiones = document.querySelector("#estado-conexiones");
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

function mostrarEstado(tipo, texto) { estado.className = `estado ${tipo}`; estadoTexto.textContent = texto; }
function desplazar() { mensajes.scrollTo({ top: mensajes.scrollHeight, behavior: "smooth" }); }
function ocultarBienvenida() { if (bienvenida) bienvenida.hidden = true; }
function agregarMensaje(texto, autor) {
  ocultarBienvenida();
  const contenedor = document.createElement("article"); contenedor.className = `mensaje ${autor}`;
  const burbuja = document.createElement("div"); burbuja.className = "burbuja";
  const etiqueta = document.createElement("span"); etiqueta.className = "autor"; etiqueta.textContent = autor === "jhony" ? "Jhony" : "ASTRO";
  const contenido = document.createElement("p"); contenido.className = "texto"; contenido.textContent = texto;
  burbuja.append(etiqueta, contenido); contenedor.appendChild(burbuja); mensajes.appendChild(contenedor); desplazar(); return contenido;
}
function agregarSistema(texto) { ocultarBienvenida(); const elemento = document.createElement("p"); elemento.className = "sistema"; elemento.textContent = texto; mensajes.appendChild(elemento); desplazar(); }
function ajustarEntrada() { entrada.style.height = "auto"; entrada.style.height = `${Math.min(entrada.scrollHeight, 132)}px`; }
function habilitarEntrada() {
  const conectado = socket && socket.readyState === WebSocket.OPEN;
  entrada.disabled = !conectado || respondiendo; enviar.disabled = !conectado || respondiendo || !entrada.value.trim();
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
    estadoModelo.textContent = datos.model;
    estadoTiempo.textContent = formatearTiempo(datos.uptime_seconds);
    estadoConexiones.textContent = String(datos.websocket_connections);
  } catch {
    estadoNucleo.textContent = "No disponible";
  }
  await actualizarEstadoPush();
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
      if (huboConexion) agregarSistema("Conexión restablecida. Comienza una sesión nueva.");
      huboConexion = true; esperaReconexion = 1000; respondiendo = false; habilitarEntrada(); entrada.focus(); return;
    }
    if (evento.type === "delta") {
      if (!respuestaActual) respuestaActual = agregarMensaje("", "astro");
      respuestaActual.textContent += evento.text; desplazar(); return;
    }
    if (evento.type === "done") {
      const registros = Array.isArray(evento.usage) ? evento.usage : [];
      const tokens = registros.reduce((total, item) => total + item.tokens, 0);
      const coste = registros.reduce((total, item) => total + item.coste_estimado_usd, 0);
      uso.textContent = `${registros.length} petición/es · ${tokens} tokens · ${coste.toFixed(6)} USD`;
      uso.hidden = false; respuestaActual = null; respondiendo = false; habilitarEntrada(); entrada.focus(); return;
    }
    if (evento.type === "error") { agregarSistema(`Error: ${evento.message}`); respuestaActual = null; respondiendo = false; habilitarEntrada(); }
  });
  socket.addEventListener("close", () => {
    if (respuestaActual) agregarSistema("La respuesta se interrumpió al perder la conexión.");
    socket = null; respuestaActual = null; respondiendo = false; habilitarEntrada(); programarReconexion();
  });
  socket.addEventListener("error", () => mostrarEstado("desconectado", "Sin conexión"));
}
formulario.addEventListener("submit", (evento) => {
  evento.preventDefault(); const texto = entrada.value.trim();
  if (!texto || !socket || socket.readyState !== WebSocket.OPEN) return;
  agregarMensaje(texto, "jhony"); socket.send(JSON.stringify({ type: "message", text: texto }));
  entrada.value = ""; ajustarEntrada(); respuestaActual = null; respondiendo = true; uso.hidden = true; habilitarEntrada();
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
    navigator.serviceWorker.register("/service-worker.js").catch(() => agregarSistema("La instalación sin conexión no está disponible."));
  });
}
pedirJSON("/push/public-key")
  .then((datos) => { clavePublicaPush = datos.public_key; })
  .catch(() => { clavePublicaPush = null; });
conectar();
