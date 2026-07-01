"use strict";

const sessionKey = "reservas-demo-session";
let sessionId = localStorage.getItem(sessionKey);
if (!sessionId) {
  sessionId = (crypto.randomUUID && crypto.randomUUID()) || String(Math.random()).slice(2);
  localStorage.setItem(sessionKey, sessionId);
}

const $mensajes = document.getElementById("mensajes");
const $form = document.getElementById("formulario");
const $entrada = document.getElementById("entrada");
const $enviar = document.getElementById("enviar");
const $reservas = document.getElementById("reservas");
const $hoy = document.getElementById("hoy");
const $modelBadge = document.getElementById("modelBadge");
const $sugerencias = document.getElementById("sugerencias");

const NOMBRE_TOOL = {
  consultar_disponibilidad: "consultó disponibilidad",
  consultar_reserva: "consultó una reserva",
  crear_reserva: "creó una reserva",
  modificar_reserva: "modificó una reserva",
  cancelar_reserva: "canceló una reserva",
};

function scrollAbajo() { $mensajes.scrollTop = $mensajes.scrollHeight; }

function burbuja(texto, clase) {
  const div = document.createElement("div");
  div.className = "msg " + clase;
  div.textContent = texto;
  $mensajes.appendChild(div);
  scrollAbajo();
  return div;
}

function notaTool(t) {
  const div = document.createElement("div");
  div.className = "tool-note";
  const a = t.args || {};
  const detalle = a.instalacion || a.nombre || a.localizador || "";
  const fecha = a.fecha ? " · " + a.fecha : "";
  const hora = a.hora_inicio ? " " + a.hora_inicio : "";
  div.innerHTML = `🔧 <b>${NOMBRE_TOOL[t.tool] || t.tool}</b> ${detalle}${fecha}${hora}`.trim();
  $mensajes.appendChild(div);
  scrollAbajo();
}

function indicadorEscribiendo() {
  const div = document.createElement("div");
  div.className = "typing";
  div.innerHTML = "<span></span><span></span><span></span>";
  $mensajes.appendChild(div);
  scrollAbajo();
  return div;
}

function renderReservas(reservas, hoy) {
  if (hoy) $hoy.textContent = hoy;
  $reservas.innerHTML = "";
  if (!reservas || !reservas.length) {
    $reservas.innerHTML = '<p class="vacio">Sin reservas todavía.</p>';
    return;
  }
  for (const r of reservas) {
    const card = document.createElement("div");
    card.className = "res-card " + (r.estado === "cancelada" ? "cancelada" : "");
    const dur = r.duracion_min >= 60 ? (r.duracion_min / 60) + " h" : r.duracion_min + " min";
    card.innerHTML = `
      <div class="r-top">
        <span class="r-inst">${r.instalacion} · ${r.recurso}</span>
        <span class="estado ${r.estado}">${r.estado}</span>
      </div>
      <div class="r-meta">${r.fecha} · ${r.hora_inicio} · ${dur} · ${r.nombre}</div>
      <div class="r-loc">${r.localizador}</div>`;
    $reservas.appendChild(card);
  }
}

async function cargarEstado() {
  try {
    const r = await fetch(`/api/state?sessionId=${encodeURIComponent(sessionId)}`);
    const j = await r.json();
    $modelBadge.textContent = j.model || "modelo";
    renderReservas(j.reservas, j.hoy);
  } catch (e) { /* ignora */ }
}

let ocupado = false;
async function enviar(texto) {
  if (ocupado || !texto.trim()) return;
  ocupado = true; $enviar.disabled = true;
  $sugerencias.style.display = "none";
  burbuja(texto, "user");
  $entrada.value = ""; ajustarAltura();
  const typing = indicadorEscribiendo();
  try {
    const r = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId, message: texto }),
    });
    const j = await r.json();
    typing.remove();
    if (!r.ok) { const e = document.createElement("div"); e.className = "error"; e.textContent = "⚠️ " + (j.error || "error"); $mensajes.appendChild(e); scrollAbajo(); }
    else {
      (j.traza || []).forEach(notaTool);
      burbuja(j.reply, "bot");
      renderReservas(j.reservas, j.hoy);
    }
  } catch (e) {
    typing.remove();
    const el = document.createElement("div"); el.className = "error"; el.textContent = "⚠️ " + e.message; $mensajes.appendChild(el);
  } finally {
    ocupado = false; $enviar.disabled = false; $entrada.focus();
  }
}

function ajustarAltura() {
  $entrada.style.height = "auto";
  $entrada.style.height = Math.min($entrada.scrollHeight, 140) + "px";
}

$form.addEventListener("submit", (e) => { e.preventDefault(); enviar($entrada.value); });
$entrada.addEventListener("input", ajustarAltura);
$entrada.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar($entrada.value); }
});
$sugerencias.querySelectorAll(".chip").forEach((c) =>
  c.addEventListener("click", () => enviar(c.textContent)));

document.getElementById("resetBtn").addEventListener("click", async () => {
  await fetch("/api/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sessionId }) });
  $mensajes.innerHTML = "";
  $sugerencias.style.display = "flex";
  await cargarEstado();
});

// Saludo inicial + estado
burbuja("¡Hola! Soy el asistente del Polideportivo Las Encinas. Puedo reservarte una instalación o consultar tus reservas. ¿Qué necesitas?", "bot");
cargarEstado();
