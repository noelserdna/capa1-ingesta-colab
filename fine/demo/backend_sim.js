/**
 * backend_sim.js — Backend SIMULADO del "Polideportivo Municipal Las Encinas".
 *
 * Puerto fiel a JavaScript de data/backend_sim.py. Es la "base de datos falsa"
 * contra la que el modelo ejecuta sus llamadas a herramientas en la demo web.
 * Determinista: la ocupación se calcula con un hash (md5) estable.
 */
"use strict";
const crypto = require("crypto");

const APERTURA_MIN = 8 * 60;   // 08:00
const CIERRE_MIN = 22 * 60;    // 22:00
const PASO_MIN = 30;           // rejilla de 30 min

// Franjas del día (hora de inicio: desde inclusive, hasta exclusive).
const FRANJAS = { manana: [8, 13], tarde: [13, 20], noche: [20, 22] };

const CATALOGO = {
  padel: { nombre: "Pádel", recursos: ["Pista 1", "Pista 2", "Pista 3", "Pista 4"],
    duraciones: [60, 90], precio_hora: 8.0, precio_persona: null,
    max_personas: 4, pregunta_personas: true, tipo: "pista" },
  tenis: { nombre: "Tenis", recursos: ["Pista 1", "Pista 2", "Pista 3"],
    duraciones: [60, 90], precio_hora: 10.0, precio_persona: null,
    max_personas: 4, pregunta_personas: true, tipo: "pista" },
  futbol_sala: { nombre: "Fútbol sala", recursos: ["Pista A", "Pista B"],
    duraciones: [60, 90], precio_hora: 30.0, precio_persona: null,
    max_personas: 14, pregunta_personas: true, tipo: "pista" },
  futbol7: { nombre: "Fútbol 7", recursos: ["Campo 1", "Campo 2"],
    duraciones: [60, 90], precio_hora: 45.0, precio_persona: null,
    max_personas: 14, pregunta_personas: true, tipo: "campo" },
  baloncesto: { nombre: "Baloncesto", recursos: ["Pista central"],
    duraciones: [60, 90], precio_hora: 25.0, precio_persona: null,
    max_personas: 12, pregunta_personas: true, tipo: "pista" },
  fronton: { nombre: "Frontón", recursos: ["Frontón"],
    duraciones: [60, 90], precio_hora: 6.0, precio_persona: null,
    max_personas: 4, pregunta_personas: false, tipo: "pista" },
  piscina: { nombre: "Piscina", recursos: ["Calle 1", "Calle 2", "Calle 3", "Calle 4", "Calle 5", "Calle 6"],
    duraciones: [60], precio_hora: null, precio_persona: 4.0,
    max_personas: 1, pregunta_personas: false, tipo: "calle" },
  spinning: { nombre: "Sala de spinning", recursos: ["Sala de spinning"],
    duraciones: [45, 60], precio_hora: null, precio_persona: 5.0,
    max_personas: 20, pregunta_personas: false, tipo: "clase" },
  tatami: { nombre: "Sala de artes marciales", recursos: ["Tatami"],
    duraciones: [60, 90], precio_hora: 12.0, precio_persona: null,
    max_personas: 20, pregunta_personas: false, tipo: "sala" },
  sala_reuniones: { nombre: "Sala de reuniones", recursos: ["Sala 1", "Sala 2"],
    duraciones: [60, 90, 120], precio_hora: 15.0, precio_persona: null,
    max_personas: 12, pregunta_personas: true, tipo: "sala" },
  sala_multiusos: { nombre: "Sala multiusos", recursos: ["Sala multiusos"],
    duraciones: [60, 120, 180], precio_hora: 20.0, precio_persona: null,
    max_personas: 50, pregunta_personas: true, tipo: "sala" },
};

const ALIAS = {
  "padel": "padel", "pádel": "padel", "tenis": "tenis",
  "futbol sala": "futbol_sala", "fútbol sala": "futbol_sala", "futsal": "futbol_sala",
  "futbol 7": "futbol7", "fútbol 7": "futbol7", "futbol siete": "futbol7", "f7": "futbol7",
  "baloncesto": "baloncesto", "basket": "baloncesto",
  "fronton": "fronton", "frontón": "fronton",
  "piscina": "piscina", "natacion": "piscina", "natación": "piscina",
  "spinning": "spinning", "ciclo": "spinning",
  "artes marciales": "tatami", "tatami": "tatami", "judo": "tatami", "karate": "tatami",
  "sala de reuniones": "sala_reuniones", "reunion": "sala_reuniones", "reunión": "sala_reuniones",
  "multiusos": "sala_multiusos", "sala multiusos": "sala_multiusos",
};

const aMinutos = (hhmm) => { const [h, m] = hhmm.split(":"); return (+h) * 60 + (+m); };
const aHHMM = (min) => `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;

function celdas(horaInicio, duracionMin) {
  const ini = aMinutos(horaInicio), out = [];
  for (let t = ini; t < ini + duracionMin; t += PASO_MIN) out.push(aHHMM(t));
  return out;
}
const esFinde = (fecha) => { const d = new Date(fecha + "T00:00:00").getDay(); return d === 0 || d === 6; };

function resolverInstalacion(texto) {
  if (texto == null) return null;
  if (CATALOGO[texto]) return texto;
  return ALIAS[String(texto).trim().toLowerCase()] || null;
}

class Backend {
  constructor(hoy, seed = 7) {
    this.hoy = hoy;          // 'YYYY-MM-DD'
    this.seed = seed;
    this.reservas = {};      // localizador -> reserva
    this._contador = 0;
  }

  _umbralOcupacion(cell, fecha) {
    const h = parseInt(cell.slice(0, 2), 10);
    let base;
    if (h >= 18 && h < 21) base = 70;
    else if (h >= 16 && h < 18) base = 45;
    else if (h >= 9 && h < 13) base = 25;
    else if (h >= 13 && h < 16) base = 15;
    else base = 35;
    if (esFinde(fecha)) base += 15;
    return Math.min(base, 95);
  }

  _ocupadoPorSimulacion(recurso, fecha, cell) {
    const clave = [this.seed, recurso, fecha, cell].join("|");
    const hex = crypto.createHash("md5").update(clave).digest("hex").slice(0, 8);
    return (parseInt(hex, 16) % 100) < this._umbralOcupacion(cell, fecha);
  }

  _celdasReservadas(fecha) {
    const ocupadas = new Set();
    for (const r of Object.values(this.reservas)) {
      if (r.estado !== "confirmada" || r.fecha !== fecha) continue;
      for (const cell of celdas(r.hora_inicio, r.duracion_min)) ocupadas.add(`${r.recurso}|${cell}`);
    }
    return ocupadas;
  }

  _recursoLibre(recurso, fecha, horaInicio, duracionMin, reservadas) {
    for (const cell of celdas(horaInicio, duracionMin)) {
      if (reservadas.has(`${recurso}|${cell}`)) return false;
      if (this._ocupadoPorSimulacion(recurso, fecha, cell)) return false;
    }
    return true;
  }

  _recursosLibres(slug, fecha, horaInicio, duracionMin) {
    const reservadas = this._celdasReservadas(fecha);
    return CATALOGO[slug].recursos.filter(
      (r) => this._recursoLibre(r, fecha, horaInicio, duracionMin, reservadas));
  }

  _horasValidas(slug, duracionMin) {
    const horas = [];
    for (let t = APERTURA_MIN; t + duracionMin <= CIERRE_MIN; t += 60) horas.push(aHHMM(t));
    return horas;
  }

  buscarHuecos(slug, fecha, duracionMin, franja = null, maxOp = 4) {
    let ini = 8, fin = 22;
    if (franja && FRANJAS[franja]) [ini, fin] = FRANJAS[franja];
    const opciones = [];
    for (const hora of this._horasValidas(slug, duracionMin)) {
      const h = parseInt(hora.slice(0, 2), 10);
      if (!(h >= ini && h < fin)) continue;
      const libres = this._recursosLibres(slug, fecha, hora, duracionMin);
      if (libres.length) opciones.push({ hora, recursos: libres });
      if (opciones.length >= maxOp) break;
    }
    return opciones;
  }

  // ----- Herramientas -----

  consultarDisponibilidad(instalacion, fecha, horaInicio = null, franja = null, duracionMin = null) {
    const slug = resolverInstalacion(instalacion);
    if (!slug) return { error: "instalacion_desconocida", instalacion };
    const dur = duracionMin || CATALOGO[slug].duraciones[0];
    const res = { instalacion: slug, fecha, hora_consultada: horaInicio, duracion_min: dur, libres: [], alternativas: [] };
    if (horaInicio) {
      res.libres = this._recursosLibres(slug, fecha, horaInicio, dur);
      if (!res.libres.length) res.alternativas = this.buscarHuecos(slug, fecha, dur, null, 3);
    } else {
      res.alternativas = this.buscarHuecos(slug, fecha, dur, franja);
    }
    return res;
  }

  consultarReserva(localizador = null, nombre = null, fecha = null) {
    if (localizador) {
      const r = this.reservas[String(localizador).toUpperCase().trim()];
      return r ? this._reservaPublica(r) : { encontrada: false };
    }
    if (nombre) {
      const objetivo = String(nombre).trim().toLowerCase();
      const cands = Object.values(this.reservas).filter(
        (r) => r.nombre.trim().toLowerCase() === objetivo && r.estado === "confirmada" &&
               (fecha == null || r.fecha === fecha));
      if (cands.length) {
        cands.sort((a, b) => (a.fecha + a.hora_inicio).localeCompare(b.fecha + b.hora_inicio));
        return this._reservaPublica(cands[0]);
      }
    }
    return { encontrada: false };
  }

  crearReserva(args) {
    const { instalacion, fecha, hora_inicio, duracion_min, nombre } = args;
    const recurso = args.recurso, num_personas = args.num_personas ?? null, contacto = args.contacto ?? null;
    const slug = resolverInstalacion(instalacion);
    if (!slug) return { ok: false, motivo: "instalacion_desconocida" };
    const info = CATALOGO[slug];
    if (fecha < this.hoy) return { ok: false, motivo: "fecha_pasada" };
    if (!info.duraciones.includes(duracion_min))
      return { ok: false, motivo: "duracion_no_valida", duraciones_validas: info.duraciones };
    if (aMinutos(hora_inicio) < APERTURA_MIN || aMinutos(hora_inicio) + duracion_min > CIERRE_MIN)
      return { ok: false, motivo: "fuera_de_horario" };
    const libres = this._recursosLibres(slug, fecha, hora_inicio, duracion_min);
    let asignado;
    if (recurso && libres.includes(recurso)) asignado = recurso;
    else if (libres.length) asignado = libres[0];
    else return { ok: false, motivo: "sin_disponibilidad", alternativas: this.buscarHuecos(slug, fecha, duracion_min, null, 3) };
    const loc = this._nuevoLocalizador();
    this.reservas[loc] = { localizador: loc, instalacion: slug, recurso: asignado,
      fecha, hora_inicio, duracion_min, nombre, num_personas, contacto, estado: "confirmada" };
    return { ok: true, localizador: loc, recurso: asignado, precio: this._precio(slug, duracion_min, num_personas) };
  }

  modificarReserva(localizador, cambios) {
    const r = this.reservas[String(localizador).toUpperCase().trim()];
    if (!r || r.estado !== "confirmada") return { ok: false, motivo: "no_encontrada" };
    for (const campo of ["fecha", "hora_inicio", "duracion_min", "recurso"])
      if (cambios[campo] != null) r[campo] = cambios[campo];
    return { ok: true, localizador: r.localizador, reserva: this._reservaPublica(r) };
  }

  cancelarReserva(localizador) {
    const r = this.reservas[String(localizador).toUpperCase().trim()];
    if (!r) return { ok: false, motivo: "no_encontrada" };
    r.estado = "cancelada";
    return { ok: true, localizador: r.localizador, estado: "cancelada" };
  }

  // Despachador: ejecuta la herramienta que pide el modelo.
  ejecutar(tool, args = {}) {
    try {
      switch (tool) {
        case "consultar_disponibilidad":
          return this.consultarDisponibilidad(args.instalacion, args.fecha, args.hora_inicio ?? null, args.franja ?? null, args.duracion_min ?? null);
        case "consultar_reserva":
          return this.consultarReserva(args.localizador ?? null, args.nombre ?? null, args.fecha ?? null);
        case "crear_reserva":
          return this.crearReserva(args);
        case "modificar_reserva":
          return this.modificarReserva(args.localizador, args.cambios ?? {});
        case "cancelar_reserva":
          return this.cancelarReserva(args.localizador);
        default:
          return { error: "herramienta_desconocida", tool };
      }
    } catch (e) {
      return { error: "argumentos_invalidos", detalle: String(e) };
    }
  }

  // ----- Ayudantes -----

  _nuevoLocalizador() {
    const alfabeto = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";
    this._contador += 1;
    const h = crypto.createHash("md5").update(`${this.seed}|loc|${this._contador}`).digest("hex");
    let chars = "";
    for (let i = 0; i < 8; i += 2) chars += alfabeto[parseInt(h.slice(i, i + 2), 16) % alfabeto.length];
    return "PM-" + chars;
  }

  _precio(slug, duracionMin, numPersonas) {
    const info = CATALOGO[slug];
    let total;
    if (info.precio_hora != null) total = info.precio_hora * duracionMin / 60;
    else total = info.precio_persona * Math.max(1, numPersonas || 1);
    return Math.abs(total - Math.round(total)) < 1e-9 ? `${Math.round(total)} €` : `${total.toFixed(2)} €`;
  }

  _reservaPublica(r) {
    return { encontrada: true, localizador: r.localizador, instalacion: CATALOGO[r.instalacion].nombre,
      recurso: r.recurso, fecha: r.fecha, hora_inicio: r.hora_inicio, duracion_min: r.duracion_min,
      nombre: r.nombre, estado: r.estado };
  }
}

// ----- System prompt (mismo texto que en Python, generado desde CATALOGO) -----

function _lineaCatalogo(slug) {
  const info = CATALOGO[slug];
  const nRec = info.recursos.length;
  const duraciones = info.duraciones.join(" o ") + " min";
  const precio = info.precio_hora != null ? `${info.precio_hora} €/hora` : `${info.precio_persona} €/persona`;
  const unidad = { pista: "pistas", campo: "campos", calle: "calles", sala: "salas", clase: "salas" }[info.tipo] || "unidades";
  const cuenta = nRec > 1 ? `${nRec} ${unidad}` : `1 ${unidad.replace(/s$/, "")}`;
  return `- ${info.nombre}: ${cuenta}. ${duraciones}. ${precio}.`;
}

function systemPrompt(fechaActual) {
  const instalaciones = Object.keys(CATALOGO).map(_lineaCatalogo).join("\n");
  return (
`Eres el asistente del Polideportivo Municipal Las Encinas. Tu único objetivo es ayudar a la gente a (1) reservar una instalación o (2) consultar, modificar o cancelar una reserva suya. Cualquier otra cosa, reconócela con amabilidad y reconduce SIEMPRE hacia eso.

Fecha actual: ${fechaActual}. Resuelve las fechas relativas ("hoy", "mañana", "el sábado") a partir de ella. El centro abre todos los días de 8:00 a 22:00.

Instalaciones:
${instalaciones}

Cómo trabajas:
- No te inventes la disponibilidad ni los datos de una reserva. Para saberlos, usa las herramientas.
- Pide los datos que falten de uno en uno, con naturalidad.
- Antes de crear, modificar o cancelar, resume y pide confirmación.
- Responde en español, en frases breves y claras.

Herramientas (las llamas escribiendo SOLO un bloque \`\`\`tool_call con un JSON {"tool": "...", "args": {...}} y nada más):
- consultar_disponibilidad(instalacion, fecha, hora_inicio?, franja?, duracion_min?)
- consultar_reserva(localizador?, nombre?, fecha?)
- crear_reserva(instalacion, fecha, hora_inicio, duracion_min, nombre, recurso?, num_personas?, contacto?)
- modificar_reserva(localizador, cambios)
- cancelar_reserva(localizador)

El sistema te devolverá el resultado en un mensaje con rol "tool". Úsalo para responder; nunca muestres el JSON al usuario.`
  );
}

module.exports = { Backend, CATALOGO, systemPrompt, resolverInstalacion };
