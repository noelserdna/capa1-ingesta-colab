"""
backend_sim.py
==============

Backend SIMULADO del "Polideportivo Municipal Las Encinas".

¿Por qué existe este fichero?
-----------------------------
Un modelo de lenguaje, por sí solo, NO sabe qué pistas están libres ni qué
reservas tiene un usuario: eso vive en una base de datos. En producción, el
modelo "llamaría a una herramienta" (una función / API) y otra parte del sistema
consultaría la base de datos de verdad.

Aquí NO tenemos base de datos real, así que la simulamos. Este módulo cumple
TRES papeles, todos con la MISMA lógica (una única fuente de verdad):

  1) Al GENERAR el dataset  -> las respuestas de disponibilidad y de estado son
     coherentes (no inventadas), porque salen de aquí.
  2) Al PROBAR el modelo en Colab -> ejecuta de verdad las herramientas que el
     modelo pide, así se prueba el bucle completo "modelo -> herramienta -> modelo".
  3) En el futuro -> este mismo código se puede envolver como servidor MCP real.

Diseño clave: DETERMINISTA.
---------------------------
Para que el dataset sea reproducible, la "ocupación" de las pistas NO es aleatoria
de verdad: se calcula con un hash (hashlib) a partir de (mundo, recurso, fecha,
hueco). Así, la misma franja siempre da el mismo resultado, pero distintas franjas
parecen ocupadas/libres de forma realista. (Ojo: NO usamos hash() de Python porque
cambia entre ejecuciones; usamos hashlib.md5, que es estable.)

Ejecuta `python backend_sim.py` para ver una demostración por pantalla.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Optional


# ---------------------------------------------------------------------------
# 1. PARÁMETROS DEL CENTRO
# ---------------------------------------------------------------------------

APERTURA_MIN = 8 * 60    # El centro abre a las 08:00 (expresado en minutos)
CIERRE_MIN = 22 * 60     # ...y cierra a las 22:00
PASO_MIN = 30            # La agenda se divide en huecos de 30 minutos

# Franjas del día (hora de inicio: desde inclusive, hasta exclusive).
# Alineadas con cómo nombramos las horas (ver hora_humana en el generador):
# 8-12 mañana, 13-20 tarde, 20-22 noche.
FRANJAS = {
    "manana": (8, 13),
    "tarde": (13, 20),
    "noche": (20, 22),
}


# ---------------------------------------------------------------------------
# 2. CATÁLOGO DE INSTALACIONES (inventado, ajústalo a tu caso real)
# ---------------------------------------------------------------------------
# Cada instalación tiene:
#   nombre            -> cómo se muestra al usuario
#   recursos          -> unidades reservables (pistas, calles, salas...)
#   duraciones        -> duraciones permitidas en minutos
#   precio_hora       -> € por hora (None si se cobra por persona)
#   precio_persona    -> € por persona (None si se cobra por hora)
#   max_personas      -> aforo típico de una reserva (None si no aplica)
#   pregunta_personas -> True si tiene sentido preguntar cuántos van a jugar
#   tipo              -> etiqueta informativa

CATALOGO = {
    "padel": {
        "nombre": "Pádel", "recursos": ["Pista 1", "Pista 2", "Pista 3", "Pista 4"],
        "duraciones": [60, 90], "precio_hora": 8.0, "precio_persona": None,
        "max_personas": 4, "pregunta_personas": True, "tipo": "pista",
    },
    "tenis": {
        "nombre": "Tenis", "recursos": ["Pista 1", "Pista 2", "Pista 3"],
        "duraciones": [60, 90], "precio_hora": 10.0, "precio_persona": None,
        "max_personas": 4, "pregunta_personas": True, "tipo": "pista",
    },
    "futbol_sala": {
        "nombre": "Fútbol sala", "recursos": ["Pista A", "Pista B"],
        "duraciones": [60, 90], "precio_hora": 30.0, "precio_persona": None,
        "max_personas": 14, "pregunta_personas": True, "tipo": "pista",
    },
    "futbol7": {
        "nombre": "Fútbol 7", "recursos": ["Campo 1", "Campo 2"],
        "duraciones": [60, 90], "precio_hora": 45.0, "precio_persona": None,
        "max_personas": 14, "pregunta_personas": True, "tipo": "campo",
    },
    "baloncesto": {
        "nombre": "Baloncesto", "recursos": ["Pista central"],
        "duraciones": [60, 90], "precio_hora": 25.0, "precio_persona": None,
        "max_personas": 12, "pregunta_personas": True, "tipo": "pista",
    },
    "fronton": {
        "nombre": "Frontón", "recursos": ["Frontón"],
        "duraciones": [60, 90], "precio_hora": 6.0, "precio_persona": None,
        "max_personas": 4, "pregunta_personas": False, "tipo": "pista",
    },
    "piscina": {
        "nombre": "Piscina", "recursos": ["Calle 1", "Calle 2", "Calle 3",
                                          "Calle 4", "Calle 5", "Calle 6"],
        "duraciones": [60], "precio_hora": None, "precio_persona": 4.0,
        "max_personas": 1, "pregunta_personas": False, "tipo": "calle",
    },
    "spinning": {
        "nombre": "Sala de spinning", "recursos": ["Sala de spinning"],
        "duraciones": [45, 60], "precio_hora": None, "precio_persona": 5.0,
        "max_personas": 20, "pregunta_personas": False, "tipo": "clase",
    },
    "tatami": {
        "nombre": "Sala de artes marciales", "recursos": ["Tatami"],
        "duraciones": [60, 90], "precio_hora": 12.0, "precio_persona": None,
        "max_personas": 20, "pregunta_personas": False, "tipo": "sala",
    },
    "sala_reuniones": {
        "nombre": "Sala de reuniones", "recursos": ["Sala 1", "Sala 2"],
        "duraciones": [60, 90, 120], "precio_hora": 15.0, "precio_persona": None,
        "max_personas": 12, "pregunta_personas": True, "tipo": "sala",
    },
    "sala_multiusos": {
        "nombre": "Sala multiusos", "recursos": ["Sala multiusos"],
        "duraciones": [60, 120, 180], "precio_hora": 20.0, "precio_persona": None,
        "max_personas": 50, "pregunta_personas": True, "tipo": "sala",
    },
}

# Cómo puede llamar el usuario a cada instalación -> a qué slug corresponde.
# Útil sobre todo en inferencia (cuando el modelo nos pasa "instalacion": "...").
ALIAS = {
    "padel": "padel", "pádel": "padel",
    "tenis": "tenis",
    "futbol sala": "futbol_sala", "fútbol sala": "futbol_sala", "futsal": "futbol_sala",
    "futbol 7": "futbol7", "fútbol 7": "futbol7", "futbol siete": "futbol7", "f7": "futbol7",
    "baloncesto": "baloncesto", "basket": "baloncesto",
    "fronton": "fronton", "frontón": "fronton",
    "piscina": "piscina", "natacion": "piscina", "natación": "piscina",
    "spinning": "spinning", "ciclo": "spinning",
    "artes marciales": "tatami", "tatami": "tatami", "judo": "tatami", "karate": "tatami",
    "sala de reuniones": "sala_reuniones", "reunion": "sala_reuniones", "reunión": "sala_reuniones",
    "multiusos": "sala_multiusos", "sala multiusos": "sala_multiusos",
}


# ---------------------------------------------------------------------------
# 3. UTILIDADES DE TIEMPO
# ---------------------------------------------------------------------------

def a_minutos(hhmm: str) -> int:
    """'18:30' -> 1110 (minutos desde medianoche)."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def a_hhmm(minutos: int) -> str:
    """1110 -> '18:30'."""
    return "{:02d}:{:02d}".format(minutos // 60, minutos % 60)


def _celdas(hora_inicio: str, duracion_min: int) -> list:
    """Devuelve los huecos de 30 min que ocupa una reserva.

    Ej.: hora 18:00, duración 90 -> ['18:00', '18:30', '19:00'].
    """
    inicio = a_minutos(hora_inicio)
    return [a_hhmm(t) for t in range(inicio, inicio + duracion_min, PASO_MIN)]


def _es_finde(fecha: str) -> bool:
    return dt.date.fromisoformat(fecha).weekday() >= 5  # 5 = sábado, 6 = domingo


def resolver_instalacion(texto: str) -> Optional[str]:
    """Convierte lo que diga el usuario/modelo ('pádel', 'futsal'...) al slug."""
    if texto in CATALOGO:
        return texto
    return ALIAS.get(texto.strip().lower())


# ---------------------------------------------------------------------------
# 3b. RESOLUCIÓN DE FECHAS (la hace el CÓDIGO, no el modelo)
# ---------------------------------------------------------------------------
# Un modelo de 2B es flojo en aritmética de fechas ("dentro de dos días" ->
# +2). Por eso el modelo solo COPIA la expresión del usuario y aquí la
# convertimos a ISO de forma fiable.

import re as _re

_NUM_PALABRA = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
                "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
                "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14}
_DIAS_SEMANA = {"lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
                "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6}
_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
          "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
          "noviembre": 11, "diciembre": 12}
_DIAS_NOMBRE = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_NOMBRE = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                 "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def resolver_fecha(texto, hoy_iso):
    """Convierte una expresión de fecha (relativa o absoluta) a ISO 'YYYY-MM-DD'.

    Devuelve None si no la entiende o es ambigua (p. ej. "el finde"), para que el
    asistente pida que la concreten.
    """
    if texto is None:
        return None
    t = str(texto).strip().lower()
    hoy = dt.date.fromisoformat(hoy_iso)
    if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):            # ya es ISO
        return t
    if t == "hoy":
        return hoy.isoformat()
    if t in ("mañana", "manana"):
        return (hoy + dt.timedelta(days=1)).isoformat()
    if "pasado mañana" in t or "pasado manana" in t or t == "pasado":
        return (hoy + dt.timedelta(days=2)).isoformat()
    m = _re.search(r"(?:dentro de|en)\s+(\d+|un|uno|una|dos|tres|cuatro|cinco|seis|"
                   r"siete|ocho|nueve|diez|once|doce|trece|catorce)\s+d[ií]as?", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _NUM_PALABRA.get(m.group(1))
        if n is not None:
            return (hoy + dt.timedelta(days=n)).isoformat()
    if (_re.search(r"(?:dentro de|en)\s+una\s+semana", t) or "semana que viene" in t
            or "próxima semana" in t or "proxima semana" in t):
        return (hoy + dt.timedelta(days=7)).isoformat()
    for nombre, wd in _DIAS_SEMANA.items():               # el/este/próximo <día>
        if _re.search(r"\b" + nombre + r"\b", t):
            delta = (wd - hoy.weekday()) % 7 or 7          # próxima aparición
            return (hoy + dt.timedelta(days=delta)).isoformat()
    m = _re.search(r"(\d{1,2})\s+de\s+([a-zéí]+)", t)      # "el 4 de julio"
    if m and _MESES.get(m.group(2)):
        dia, mes = int(m.group(1)), _MESES[m.group(2)]
        anio = hoy.year
        try:
            cand = dt.date(anio, mes, dia)
        except ValueError:
            return None
        if cand < hoy:
            cand = dt.date(anio + 1, mes, dia)
        return cand.isoformat()
    m = _re.search(r"d[ií]a\s+(\d{1,2})", t)               # "el día 15"
    if m:
        dia, anio, mes = int(m.group(1)), hoy.year, hoy.month
        for _ in range(13):
            try:
                cand = dt.date(anio, mes, dia)
                if cand >= hoy:
                    return cand.isoformat()
            except ValueError:
                pass
            mes += 1
            if mes > 12:
                mes, anio = 1, anio + 1
    return None


def fecha_humana(iso, hoy_iso):
    """ISO -> forma natural relativa a hoy ('mañana', 'el jueves 4 de julio')."""
    d = dt.date.fromisoformat(iso)
    delta = (d - dt.date.fromisoformat(hoy_iso)).days
    if delta == 0:
        return "hoy"
    if delta == 1:
        return "mañana"
    if delta == 2:
        return "pasado mañana"
    return "el %s %d de %s" % (_DIAS_NOMBRE[d.weekday()], d.day, _MESES_NOMBRE[d.month - 1])


# ---------------------------------------------------------------------------
# 4. EL BACKEND
# ---------------------------------------------------------------------------

class Backend:
    """Una "base de datos" en memoria de un día concreto del polideportivo.

    Cada conversación del dataset usa SU PROPIO Backend (su propio "mundo"), con:
      - `hoy`  : la fecha actual de esa conversación (para validar y resolver
                 fechas relativas como "mañana").
      - `seed` : la semilla del mundo, que hace que la ocupación simulada sea
                 distinta entre conversaciones pero estable dentro de una.
    """

    def __init__(self, hoy: str, seed: int = 0):
        self.hoy = hoy            # 'YYYY-MM-DD'
        self.seed = seed
        self.reservas = {}        # localizador -> dict de reserva
        self._contador = 0        # para generar localizadores únicos

    # ----- 4.1 Ocupación simulada (determinista) ---------------------------

    def _umbral_ocupacion(self, cell: str, fecha: str) -> int:
        """Probabilidad (0-100) de que un hueco esté ocupado, según la hora.

        Las horas punta (tardes) salen más ocupadas: así el modelo aprende a
        ofrecer alternativas cuando no hay sitio.
        """
        h = int(cell[:2])
        if 18 <= h < 21:
            base = 70       # franja punta de tarde
        elif 16 <= h < 18:
            base = 45
        elif 9 <= h < 13:
            base = 25       # mañana tranquila
        elif 13 <= h < 16:
            base = 15       # mediodía muy tranquilo
        else:
            base = 35
        if _es_finde(fecha):
            base += 15      # los findes hay más gente
        return min(base, 95)

    def _ocupado_por_simulacion(self, recurso: str, fecha: str, cell: str) -> bool:
        """Decisión DETERMINISTA de si un hueco está ocupado de fondo."""
        clave = "|".join([str(self.seed), recurso, fecha, cell])
        valor = int(hashlib.md5(clave.encode("utf-8")).hexdigest()[:8], 16) % 100
        return valor < self._umbral_ocupacion(cell, fecha)

    def _celdas_reservadas(self, fecha: str) -> set:
        """Huecos ya ocupados por reservas REALES (creadas en este mundo)."""
        ocupadas = set()
        for r in self.reservas.values():
            if r["estado"] != "confirmada" or r["fecha"] != fecha:
                continue
            for cell in _celdas(r["hora_inicio"], r["duracion_min"]):
                ocupadas.add((r["recurso"], cell))
        return ocupadas

    def _recurso_libre(self, recurso, fecha, hora_inicio, duracion_min, reservadas):
        """¿Está ESTE recurso (pista/sala) libre en ese tramo concreto?"""
        for cell in _celdas(hora_inicio, duracion_min):
            if (recurso, cell) in reservadas:
                return False
            if self._ocupado_por_simulacion(recurso, fecha, cell):
                return False
        return True

    def _recursos_libres(self, slug, fecha, hora_inicio, duracion_min) -> list:
        """Lista de recursos libres de una instalación en un tramo."""
        reservadas = self._celdas_reservadas(fecha)
        libres = []
        for recurso in CATALOGO[slug]["recursos"]:
            if self._recurso_libre(recurso, fecha, hora_inicio, duracion_min, reservadas):
                libres.append(recurso)
        return libres

    def _horas_validas(self, slug, duracion_min) -> list:
        """Horas de inicio en punto que caben antes del cierre."""
        horas = []
        t = APERTURA_MIN
        while t + duracion_min <= CIERRE_MIN:
            horas.append(a_hhmm(t))
            t += 60   # en punto, para listar opciones limpias
        return horas

    def buscar_huecos(self, slug, fecha, duracion_min, franja=None, max_op=4) -> list:
        """Devuelve [{'hora': ..., 'recursos': [...]}] con disponibilidad."""
        if franja and franja in FRANJAS:
            ini, fin = FRANJAS[franja]
        else:
            ini, fin = 8, 22
        opciones = []
        for hora in self._horas_validas(slug, duracion_min):
            if not (ini <= int(hora[:2]) < fin):
                continue
            libres = self._recursos_libres(slug, fecha, hora, duracion_min)
            if libres:
                opciones.append({"hora": hora, "recursos": libres})
            if len(opciones) >= max_op:
                break
        return opciones

    # ----- 4.2 HERRAMIENTAS (lo que el modelo puede llamar) -----------------

    def consultar_disponibilidad(self, instalacion, fecha,
                                 hora_inicio=None, franja=None, duracion_min=None):
        """Lectura: ¿qué hay libre?"""
        slug = resolver_instalacion(instalacion)
        if slug is None:
            return {"error": "instalacion_desconocida", "instalacion": instalacion}
        iso = resolver_fecha(fecha, self.hoy)   # el código resuelve la fecha
        if iso is None:
            return {"error": "fecha_no_entendida", "fecha_recibida": fecha}
        fecha = iso
        dur = duracion_min or CATALOGO[slug]["duraciones"][0]

        resultado = {
            "instalacion": slug,
            "fecha": fecha,
            "fecha_humana": fecha_humana(fecha, self.hoy),
            "hora_consultada": hora_inicio,
            "duracion_min": dur,
            "libres": [],
            "alternativas": [],
        }

        if hora_inicio:
            resultado["libres"] = self._recursos_libres(slug, fecha, hora_inicio, dur)
            if not resultado["libres"]:
                # No hay a esa hora -> proponemos otras horas del día con sitio.
                resultado["alternativas"] = self.buscar_huecos(slug, fecha, dur, max_op=3)
        else:
            # Sin hora concreta -> listamos opciones (de la franja, si la hay).
            resultado["alternativas"] = self.buscar_huecos(slug, fecha, dur, franja=franja)
        return resultado

    def consultar_reserva(self, localizador=None, nombre=None, fecha=None):
        """Lectura: estado de una reserva, por localizador o por nombre."""
        if localizador:
            r = self.reservas.get(localizador.upper().strip())
            if r:
                return self._reserva_publica(r)
            return {"encontrada": False}
        if nombre:
            objetivo = nombre.strip().lower()
            iso = resolver_fecha(fecha, self.hoy) if fecha else None
            candidatas = [
                r for r in self.reservas.values()
                if r["nombre"].strip().lower() == objetivo
                and r["estado"] == "confirmada"
                and (iso is None or r["fecha"] == iso)
            ]
            if candidatas:
                candidatas.sort(key=lambda r: (r["fecha"], r["hora_inicio"]))
                return self._reserva_publica(candidatas[0])
        return {"encontrada": False}

    def crear_reserva(self, instalacion, fecha, hora_inicio, duracion_min,
                      nombre, recurso=None, num_personas=None, contacto=None):
        """Escritura: crea la reserva (validando todo)."""
        slug = resolver_instalacion(instalacion)
        if slug is None:
            return {"ok": False, "motivo": "instalacion_desconocida"}
        info = CATALOGO[slug]

        iso = resolver_fecha(fecha, self.hoy)   # el código resuelve la fecha
        if iso is None:
            return {"ok": False, "motivo": "fecha_no_entendida", "fecha_recibida": fecha}
        fecha = iso

        # Validaciones de sentido común -> dan material para casos de error.
        if fecha < self.hoy:
            return {"ok": False, "motivo": "fecha_pasada"}
        if duracion_min not in info["duraciones"]:
            return {"ok": False, "motivo": "duracion_no_valida",
                    "duraciones_validas": info["duraciones"]}
        if a_minutos(hora_inicio) < APERTURA_MIN or \
           a_minutos(hora_inicio) + duracion_min > CIERRE_MIN:
            return {"ok": False, "motivo": "fuera_de_horario"}

        # ¿Hay un recurso libre? (respetamos el pedido si está libre)
        libres = self._recursos_libres(slug, fecha, hora_inicio, duracion_min)
        if recurso and recurso in libres:
            asignado = recurso
        elif libres:
            asignado = libres[0]
        else:
            return {"ok": False, "motivo": "sin_disponibilidad",
                    "alternativas": self.buscar_huecos(slug, fecha, duracion_min, max_op=3)}

        loc = self._nuevo_localizador()
        self.reservas[loc] = {
            "localizador": loc, "instalacion": slug, "recurso": asignado,
            "fecha": fecha, "hora_inicio": hora_inicio, "duracion_min": duracion_min,
            "nombre": nombre, "num_personas": num_personas, "contacto": contacto,
            "estado": "confirmada",
        }
        return {"ok": True, "localizador": loc, "recurso": asignado,
                "fecha": fecha, "fecha_humana": fecha_humana(fecha, self.hoy),
                "precio": self._precio(slug, duracion_min, num_personas)}

    def modificar_reserva(self, localizador, cambios):
        """Escritura: cambia hora/fecha/duración/recurso de una reserva."""
        r = self.reservas.get(str(localizador).upper().strip())
        if not r or r["estado"] != "confirmada":
            return {"ok": False, "motivo": "no_encontrada"}
        if cambios.get("fecha"):                       # el código resuelve la fecha
            iso = resolver_fecha(cambios["fecha"], self.hoy)
            if iso:
                r["fecha"] = iso
        for campo in ("hora_inicio", "duracion_min", "recurso"):
            if cambios.get(campo) is not None:
                r[campo] = cambios[campo]
        return {"ok": True, "localizador": r["localizador"],
                "reserva": self._reserva_publica(r)}

    def cancelar_reserva(self, localizador):
        """Escritura: marca la reserva como cancelada."""
        r = self.reservas.get(str(localizador).upper().strip())
        if not r:
            return {"ok": False, "motivo": "no_encontrada"}
        r["estado"] = "cancelada"
        return {"ok": True, "localizador": r["localizador"], "estado": "cancelada"}

    # ----- 4.3 Despachador: ejecutar una llamada {tool, args} ---------------

    def ejecutar(self, tool: str, args: dict) -> dict:
        """Ejecuta la herramienta que pide el modelo. Lo usa el notebook."""
        fns = {
            "consultar_disponibilidad": self.consultar_disponibilidad,
            "consultar_reserva": self.consultar_reserva,
            "crear_reserva": self.crear_reserva,
            "modificar_reserva": self.modificar_reserva,
            "cancelar_reserva": self.cancelar_reserva,
        }
        if tool not in fns:
            return {"error": "herramienta_desconocida", "tool": tool}
        try:
            return fns[tool](**args)
        except TypeError as e:
            return {"error": "argumentos_invalidos", "detalle": str(e)}

    # ----- 4.4 Ayudantes internos -----------------------------------------

    def _nuevo_localizador(self) -> str:
        """Localizador tipo 'PM-7G2K' (estable dentro de un mundo)."""
        alfabeto = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sin 0/O/1/I/L para no confundir
        self._contador += 1
        clave = "{}|loc|{}".format(self.seed, self._contador)
        h = hashlib.md5(clave.encode("utf-8")).hexdigest()
        chars = [alfabeto[int(h[i:i + 2], 16) % len(alfabeto)] for i in range(0, 8, 2)]
        return "PM-" + "".join(chars)

    def _precio(self, slug, duracion_min, num_personas) -> str:
        info = CATALOGO[slug]
        if info["precio_hora"] is not None:
            total = info["precio_hora"] * duracion_min / 60.0
        else:
            total = info["precio_persona"] * max(1, num_personas or 1)
        if abs(total - round(total)) < 1e-9:
            return "{:d} €".format(int(round(total)))
        return "{:.2f} €".format(total)

    def _reserva_publica(self, r: dict) -> dict:
        """Versión de la reserva que se devuelve como resultado de herramienta."""
        return {
            "encontrada": True,
            "localizador": r["localizador"],
            "instalacion": CATALOGO[r["instalacion"]]["nombre"],
            "recurso": r["recurso"],
            "fecha": r["fecha"],
            "hora_inicio": r["hora_inicio"],
            "duracion_min": r["duracion_min"],
            "nombre": r["nombre"],
            "estado": r["estado"],
        }


# ---------------------------------------------------------------------------
# 5. SYSTEM PROMPT (se construye a partir del MISMO catálogo, sin duplicar nada)
# ---------------------------------------------------------------------------

def _linea_catalogo(slug: str) -> str:
    """Genera la línea descriptiva de una instalación para el system prompt."""
    info = CATALOGO[slug]
    n_rec = len(info["recursos"])
    duraciones = " o ".join(str(d) for d in info["duraciones"]) + " min"
    if info["precio_hora"] is not None:
        precio = "{:g} €/hora".format(info["precio_hora"])
    else:
        precio = "{:g} €/persona".format(info["precio_persona"])
    unidad = {"pista": "pistas", "campo": "campos", "calle": "calles",
              "sala": "salas", "clase": "salas"}.get(info["tipo"], "unidades")
    cuenta = "{} {}".format(n_rec, unidad) if n_rec > 1 else "1 {}".format(unidad[:-1] if unidad.endswith("s") else unidad)
    return "- {}: {}. {}. {}.".format(info["nombre"], cuenta, duraciones, precio)


def system_prompt(fecha_actual: str) -> str:
    """Devuelve el system prompt completo para una fecha dada.

    Es el MISMO que va en data/ESQUEMA.md y en deploy/system_prompt.txt, pero
    aquí el bloque de instalaciones se genera desde CATALOGO para que nunca se
    desincronice del backend.
    """
    instalaciones = "\n".join(_linea_catalogo(s) for s in CATALOGO)
    return (
        "Eres el asistente del Polideportivo Municipal Las Encinas. Tu único "
        "objetivo es ayudar a la gente a (1) reservar una instalación o (2) "
        "consultar, modificar o cancelar una reserva suya. Cualquier otra cosa, "
        "reconócela con amabilidad y reconduce SIEMPRE hacia eso.\n\n"
        "Fecha actual: {fecha}. El centro abre todos los días de 8:00 a 22:00.\n\n"
        "Instalaciones:\n{instalaciones}\n\n"
        "Cómo trabajas:\n"
        "- No te inventes la disponibilidad ni los datos de una reserva. Para "
        "saberlos, usa las herramientas.\n"
        "- FECHAS: no las calcules tú. En el campo \"fecha\" escribe TAL CUAL lo "
        "que diga el usuario (\"mañana\", \"dentro de dos días\", \"el sábado\", "
        "\"el 4 de julio\"); el sistema te devolverá la fecha ya resuelta en "
        "\"fecha_humana\", y esa es la que dices al usuario. Si la fecha es "
        "ambigua (p. ej. \"el finde\"), pide que la concrete.\n"
        "- DURACIÓN: respeta las duraciones válidas de cada instalación; si piden "
        "uno no válido, ofréceles las opciones correctas.\n"
        "- Pide los datos que falten de uno en uno, con naturalidad.\n"
        "- Antes de crear, modificar o cancelar, resume y pide confirmación.\n"
        "- Responde en español, en frases breves y claras.\n\n"
        "Herramientas (las llamas escribiendo SOLO un bloque ```tool_call con un "
        "JSON {{\"tool\": \"...\", \"args\": {{...}}}} y nada más):\n"
        "- consultar_disponibilidad(instalacion, fecha, hora_inicio?, franja?, duracion_min?)\n"
        "- consultar_reserva(localizador?, nombre?, fecha?)\n"
        "- crear_reserva(instalacion, fecha, hora_inicio, duracion_min, nombre, recurso?, num_personas?, contacto?)\n"
        "- modificar_reserva(localizador, cambios)\n"
        "- cancelar_reserva(localizador)\n\n"
        "El sistema te devolverá el resultado en un mensaje con rol \"tool\". "
        "Úsalo para responder; nunca muestres el JSON al usuario."
    ).format(fecha=fecha_actual, instalaciones=instalaciones)


# ---------------------------------------------------------------------------
# 6. DEMOSTRACIÓN (se ejecuta con: python backend_sim.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== DEMO del backend simulado ===\n")
    bk = Backend(hoy="2026-09-01", seed=7)

    print(">> system_prompt('2026-09-01'):\n")
    print(system_prompt("2026-09-01"))
    print("\n" + "-" * 70 + "\n")

    print(">> Disponibilidad de pádel el 2026-09-05 a las 19:00 (hora punta):")
    print(json.dumps(bk.consultar_disponibilidad("padel", "2026-09-05",
          hora_inicio="19:00", duracion_min=60), ensure_ascii=False, indent=2))

    print("\n>> Crear una reserva de tenis:")
    res = bk.crear_reserva("tenis", "2026-09-05", "11:00", 60, "Marta Ruiz", num_personas=2)
    print(json.dumps(res, ensure_ascii=False))

    print("\n>> Consultar esa reserva por nombre:")
    print(json.dumps(bk.consultar_reserva(nombre="Marta Ruiz"), ensure_ascii=False))

    print("\n>> Cancelarla:")
    print(json.dumps(bk.cancelar_reserva(res["localizador"]), ensure_ascii=False))
