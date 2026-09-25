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
let socket = null;
let respuestaActual = null;
let respondiendo = false;
let reintento = null;
let esperaReconexion = 1000;
let huboConexion = false;

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
window.addEventListener("online", conectar);
window.addEventListener("offline", () => { mostrarEstado("desconectado", "Sin red"); habilitarEntrada(); });
document.addEventListener("visibilitychange", () => { if (!document.hidden) conectar(); });
if (window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone) instalar.hidden = true;
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch(() => agregarSistema("La instalación sin conexión no está disponible."));
  });
}
conectar();
