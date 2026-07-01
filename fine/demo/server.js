/**
 * server.js — Demo web del asistente de reservas.
 *
 * Sirve el chat (public/) y expone una API que ejecuta el BUCLE DE HERRAMIENTAS:
 *   usuario -> modelo (Ollama) -> si pide tool_call, backend_sim lo ejecuta ->
 *   se le devuelve el resultado -> repite hasta que el modelo responde.
 *
 * El modelo se sirve con Ollama. Config por variables de entorno:
 *   OLLAMA_URL (def. http://127.0.0.1:11434)
 *   MODEL      (def. "reservas"; usa "gemma4:e2b" para probar con el base)
 *   PORT       (def. 3000)
 */
"use strict";
const express = require("express");
const path = require("path");
const { Backend, CATALOGO, systemPrompt } = require("./backend_sim");

const OLLAMA_URL = process.env.OLLAMA_URL || "http://127.0.0.1:11434";
const MODEL = process.env.MODEL || "reservas";
const PORT = process.env.PORT || 3000;

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

// ---- Sesiones en memoria (una conversación + su backend por sessionId) ----
const sesiones = new Map();

function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

function sembrarDemo(bk) {
  // Un par de reservas de ejemplo para poder probar "consultar/cancelar" ya.
  const siembra = [
    { inst: "padel", nombre: "Marta Ruiz", personas: 4 },
    { inst: "tenis", nombre: "Carlos Gil", personas: 2 },
  ];
  for (const s of siembra) {
    for (let extra = 2; extra < 12; extra++) {
      const f = new Date(Date.now() + extra * 864e5).toISOString().slice(0, 10);
      const hue = bk.buscarHuecos(s.inst, f, 60, null, 1);
      if (hue.length) {
        bk.crearReserva({ instalacion: s.inst, fecha: f, hora_inicio: hue[0].hora,
          duracion_min: 60, nombre: s.nombre, num_personas: s.personas });
        break;
      }
    }
  }
}

function getSesion(id) {
  if (!sesiones.has(id)) {
    const hoy = hoyISO();
    const backend = new Backend(hoy, 7);
    sembrarDemo(backend);
    sesiones.set(id, { backend, messages: [{ role: "system", content: systemPrompt(hoy) }], hoy });
  }
  return sesiones.get(id);
}

function reservasPublicas(bk) {
  return Object.values(bk.reservas).map((r) => ({
    localizador: r.localizador, instalacion: CATALOGO[r.instalacion].nombre,
    recurso: r.recurso, fecha: r.fecha, hora_inicio: r.hora_inicio,
    duracion_min: r.duracion_min, nombre: r.nombre, estado: r.estado,
  }));
}

// ---- Cliente de Ollama + extracción de tool_call ----

async function llamarModelo(messages) {
  const body = { model: MODEL, messages, stream: false, options: { temperature: 0.3, top_p: 0.95 } };
  let resp;
  try {
    resp = await fetch(OLLAMA_URL + "/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  } catch (e) {
    throw new Error(`No pude conectar con Ollama en ${OLLAMA_URL}. ¿Está arrancado? (ollama serve)`);
  }
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`Ollama respondió ${resp.status}: ${txt.slice(0, 300)}`);
  }
  const j = await resp.json();
  return ((j.message && j.message.content) || "").trim();
}

function extraerToolCall(texto) {
  const m = texto.match(/```tool_call\s*(\{[\s\S]*?\})\s*```/);
  if (!m) return null;
  try { return JSON.parse(m[1]); } catch (e) { return null; }
}

async function turnoChat(sesion, textoUsuario) {
  sesion.messages.push({ role: "user", content: textoUsuario });
  const traza = [];
  for (let i = 0; i < 6; i++) {
    const salida = await llamarModelo(sesion.messages);
    sesion.messages.push({ role: "assistant", content: salida });
    const tc = extraerToolCall(salida);
    if (!tc) return { reply: salida, traza };
    const resultado = sesion.backend.ejecutar(tc.tool, tc.args || {});
    traza.push({ tool: tc.tool, args: tc.args || {}, result: resultado });
    // El resultado vuelve como turno de usuario envuelto (igual que en el entrenamiento).
    sesion.messages.push({ role: "user", content: "```tool_result\n" + JSON.stringify(resultado) + "\n```" });
  }
  return { reply: "Lo siento, no he podido completar la operación.", traza };
}

// ---- API ----

app.post("/api/chat", async (req, res) => {
  const { sessionId, message } = req.body || {};
  if (!sessionId || !message) return res.status(400).json({ error: "faltan sessionId o message" });
  const sesion = getSesion(sessionId);
  try {
    const { reply, traza } = await turnoChat(sesion, message);
    res.json({ reply, traza, reservas: reservasPublicas(sesion.backend), hoy: sesion.hoy });
  } catch (e) {
    res.status(502).json({ error: String(e.message || e) });
  }
});

app.get("/api/state", (req, res) => {
  const id = req.query.sessionId;
  if (!id) return res.json({ reservas: [], hoy: hoyISO(), model: MODEL });
  const s = getSesion(id);   // crea la sesión (con reservas sembradas) si no existía
  res.json({ reservas: reservasPublicas(s.backend), hoy: s.hoy, model: MODEL });
});

app.post("/api/reset", (req, res) => {
  const { sessionId } = req.body || {};
  if (sessionId) sesiones.delete(sessionId);
  res.json({ ok: true });
});

app.listen(PORT, () => {
  console.log(`\n  Demo de reservas en  http://localhost:${PORT}`);
  console.log(`  Modelo (Ollama): ${MODEL}   ·   Ollama: ${OLLAMA_URL}\n`);
});
