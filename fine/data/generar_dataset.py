"""
generar_dataset.py
==================

Genera el dataset sintético de conversaciones para el fine-tuning del asistente
de reservas. Cada conversación se "actúa" contra el backend simulado
(`backend_sim.py`), de modo que las llamadas a herramientas y sus resultados son
SIEMPRE coherentes.

Idea mental: este script es como un "guionista" que, para cada conversación:
  1. inventa un escenario (qué quiere el usuario, cuántos datos da de golpe...),
  2. simula al usuario y al asistente turno a turno,
  3. cuando el asistente necesita datos reales (disponibilidad, estado de una
     reserva...), llama de verdad al backend y usa lo que devuelve.

Uso:
  # Ver una muestra legible por pantalla (no escribe ficheros):
  python generar_dataset.py --muestra 8

  # Generar el dataset completo (train + val):
  python generar_dataset.py --n 1200 --salida dataset.jsonl

Reproducibilidad: con la misma --semilla siempre sale exactamente lo mismo.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta

import backend_sim as B


# ===========================================================================
# 1. BANCOS DE TEXTO (para que las conversaciones no suenen todas iguales)
# ===========================================================================

NOMBRES = ["Andrés", "Marta", "Javier", "Lucía", "Carlos", "Ana", "Pablo",
           "Elena", "Sergio", "Laura", "Miguel", "Sara", "David", "Nuria",
           "Jorge", "Cristina", "Raúl", "Patricia", "Alberto", "Beatriz",
           "Iván", "Marina", "Rubén", "Carmen", "Diego", "Paula", "Hugo",
           "Alba", "Adrián", "Noelia"]

APELLIDOS = ["García", "Martínez", "López", "Sánchez", "Pérez", "Gómez", "Ruiz",
             "Díaz", "Fernández", "Moreno", "Jiménez", "Romero", "Navarro",
             "Torres", "Vázquez", "Ramos", "Gil", "Serrano", "Castro", "Ortega"]

SALUDOS = ["Hola", "Buenas", "Hola, buenas", "Hola qué tal", "Buenos días",
           "Buenas tardes", "Hola!", "", ""]

GRACIAS = ["gracias", "muchas gracias", "vale, gracias", "perfecto, gracias",
           "genial, gracias", "ok, gracias", "estupendo, gracias"]

SI = ["sí", "sí, perfecto", "sí por favor", "correcto", "eso es", "vale, sí",
      "sí adelante", "perfecto", "venga, sí"]

VERBOS_RESERVA = ["quiero reservar", "quería reservar", "me gustaría reservar",
                  "necesito reservar", "quería coger", "me apunto a reservar"]

# Cómo nombra el usuario cada instalación (slug -> formas de decirlo).
TERMINOS = {
    "padel": ["una pista de pádel", "pádel", "una de pádel"],
    "tenis": ["una pista de tenis", "tenis", "una de tenis"],
    "futbol_sala": ["la pista de fútbol sala", "fútbol sala", "futsal"],
    "futbol7": ["un campo de fútbol 7", "fútbol 7", "fútbol siete"],
    "baloncesto": ["la pista de baloncesto", "baloncesto", "una pista de basket"],
    "fronton": ["el frontón", "una pista de frontón"],
    "piscina": ["una calle de la piscina", "la piscina", "para nadar"],
    "spinning": ["una clase de spinning", "spinning"],
    "tatami": ["la sala de artes marciales", "el tatami"],
    "sala_reuniones": ["una sala de reuniones", "la sala de reuniones"],
    "sala_multiusos": ["la sala multiusos", "la sala grande"],
}

# Peso de cada instalación al elegir (las deportivas, más probables).
PESOS_INSTALACION = {
    "padel": 26, "tenis": 16, "futbol_sala": 12, "futbol7": 9, "baloncesto": 7,
    "fronton": 4, "piscina": 9, "spinning": 4, "tatami": 3,
    "sala_reuniones": 6, "sala_multiusos": 4,
}

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
NUM12 = {1: "una", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis",
         7: "siete", 8: "ocho", 9: "nueve", 10: "diez", 11: "once", 12: "doce"}


# ===========================================================================
# 2. AYUDANTES DE TEXTO Y DE FECHAS/HORAS
# ===========================================================================

def nombre_completo(rng):
    return "{} {}".format(rng.choice(NOMBRES), rng.choice(APELLIDOS))


def telefono(rng):
    return rng.choice("67") + "".join(rng.choice("0123456789") for _ in range(8))


def elegir_instalacion(rng):
    slugs = list(PESOS_INSTALACION.keys())
    pesos = [PESOS_INSTALACION[s] for s in slugs]
    return rng.choices(slugs, weights=pesos, k=1)[0]


def _sufijo_dia(h):
    if h < 12:
        return "de la mañana"
    if h == 12:
        return "del mediodía"
    if h < 21:
        return "de la tarde"
    return "de la noche"


def hora_humana(hhmm):
    """'20:00' -> 'las ocho de la tarde' (como lo diría el asistente)."""
    h = int(hhmm[:2])
    h12 = h % 12 or 12
    base = "la una" if h12 == 1 else "las {}".format(NUM12[h12])
    return "{} {}".format(base, _sufijo_dia(h))


def frase_hora_usuario(rng, franja=None):
    """Elige una hora y una forma natural de que la diga el usuario.

    Devuelve (frase, 'HH:00').
    """
    if franja == "manana":
        h = rng.choice([9, 10, 11, 12])
    elif franja == "tarde":
        h = rng.choice([16, 17, 18, 19])
    elif franja == "noche":
        h = rng.choice([20, 21])
    else:
        h = rng.choice([9, 10, 11, 12, 16, 17, 18, 19, 20])
    hhmm = "{:02d}:00".format(h)
    estilo = rng.choice(["humana", "humana", "24h", "corta"])
    if estilo == "24h":
        return "a las {}".format(hhmm), hhmm
    if estilo == "corta":
        h12 = h % 12 or 12
        return "a las {}".format(h12), hhmm
    return "a {}".format(hora_humana(hhmm)), hhmm


def frase_duracion(dur):
    return {45: "tres cuartos de hora", 60: "una hora", 90: "hora y media",
            120: "dos horas", 180: "tres horas"}.get(dur, "{} minutos".format(dur))


def fecha_concreta(hoy, rng):
    """Devuelve (frase_usuario, fecha_iso) con una fecha FUTURA concreta."""
    estilo = rng.choices(
        ["manana", "pasado", "dia_semana", "dia_mes"],
        weights=[3, 1, 4, 2], k=1)[0]
    if estilo == "manana":
        d = hoy + timedelta(days=1)
        return "mañana", d.isoformat()
    if estilo == "pasado":
        d = hoy + timedelta(days=2)
        return "pasado mañana", d.isoformat()
    if estilo == "dia_semana":
        d = hoy + timedelta(days=rng.randint(2, 8))
        pre = rng.choice(["el", "este", "el próximo"])
        return "{} {}".format(pre, DIAS[d.weekday()]), d.isoformat()
    d = hoy + timedelta(days=rng.randint(3, 25))
    return "el {} de {}".format(d.day, MESES[d.month - 1]), d.isoformat()


def humana_fecha(iso, hoy):
    """ISO -> forma natural relativa a hoy ('mañana', 'el sábado 6 de septiembre')."""
    d = date.fromisoformat(iso)
    delta = (d - hoy).days
    if delta == 0:
        return "hoy"
    if delta == 1:
        return "mañana"
    if delta == 2:
        return "pasado mañana"
    return "el {} {} de {}".format(DIAS[d.weekday()], d.day, MESES[d.month - 1])


def proximo_dia_semana(hoy, objetivo_wd):
    """Próxima fecha cuyo día de la semana sea `objetivo_wd` (0=lunes ... 6=domingo)."""
    delta = (objetivo_wd - hoy.weekday()) % 7
    return hoy + timedelta(days=delta or 7)


# ===========================================================================
# 3. CONSTRUCTORES DE MENSAJES (azúcar para no repetir dicts a mano)
# ===========================================================================

def usr(texto):
    return {"role": "user", "content": texto}


def asst(texto):
    return {"role": "assistant", "content": texto}


def tool_call(tool, args):
    """Turno del asistente que es SOLO una llamada a herramienta."""
    cuerpo = json.dumps({"tool": tool, "args": args}, ensure_ascii=False)
    return {"role": "assistant", "content": "```tool_call\n" + cuerpo + "\n```"}


def tool_result(resultado):
    """Turno con rol 'tool': lo que devuelve el backend."""
    return {"role": "tool", "content": json.dumps(resultado, ensure_ascii=False)}


# ===========================================================================
# 4. CONSTRUCTORES DE CONVERSACIÓN (uno por intención)
# ===========================================================================

def cerrar_reserva(bk, hoy, rng, slug, fecha, hora, dur, nombre, num_personas):
    """Tramo final compartido: consultar -> (alternativa si hace falta) ->
    confirmar -> crear -> cierre. Devuelve (lista_de_mensajes, escenario).

    Lo usan varios constructores para no repetir esta lógica.
    """
    info = B.CATALOGO[slug]
    msgs = []
    escenario = "directo"

    res = bk.consultar_disponibilidad(slug, fecha, hora_inicio=hora, duracion_min=dur)
    msgs.append(tool_call("consultar_disponibilidad",
                {"instalacion": slug, "fecha": fecha, "hora_inicio": hora,
                 "duracion_min": dur}))
    msgs.append(tool_result(res))

    if not res["libres"]:
        alts = res["alternativas"]
        if alts:
            propuestas = alts[:2]
            horas_txt = " o a ".join(hora_humana(a["hora"]) for a in propuestas)
            msgs.append(asst("A esa hora no me queda nada libre. Sí tengo a {}. "
                             "¿Cuál prefieres?".format(horas_txt)))
            hora = rng.choice(propuestas)["hora"]
            msgs.append(usr(rng.choice(["pues a {}".format(hora_humana(hora)),
                                        "vale, a {}".format(hora_humana(hora)),
                                        "la de {}".format(hora_humana(hora))])))
            escenario = "alternativa_hora"
        else:
            escenario = "alternativa_dia"
            d2 = (date.fromisoformat(fecha) + timedelta(days=1)).isoformat()
            res_d2 = bk.consultar_disponibilidad(slug, d2, duracion_min=dur)
            msgs.append(asst("Ese día lo tengo completo. Déjame mirar el siguiente."))
            msgs.append(tool_call("consultar_disponibilidad",
                        {"instalacion": slug, "fecha": d2, "duracion_min": dur}))
            msgs.append(tool_result(res_d2))
            if res_d2["alternativas"]:
                op = res_d2["alternativas"][0]
                fecha, hora = d2, op["hora"]
                msgs.append(asst("El {} sí tengo hueco a {}. ¿Te vale?".format(
                    humana_fecha(fecha, hoy), hora_humana(hora))))
                msgs.append(usr(rng.choice(SI)))

    resumen = "{} {} a {}, {}, a nombre de {}".format(
        info["nombre"], humana_fecha(fecha, hoy), hora_humana(hora),
        frase_duracion(dur), nombre)
    msgs.append(asst("Te confirmo: {}. ¿La reservo?".format(resumen)))
    msgs.append(usr(rng.choice(SI)))

    args = {"instalacion": slug, "fecha": fecha, "hora_inicio": hora,
            "duracion_min": dur, "nombre": nombre}
    if info["pregunta_personas"] and num_personas:
        args["num_personas"] = num_personas
    res2 = bk.crear_reserva(**args)
    msgs.append(tool_call("crear_reserva", args))
    msgs.append(tool_result(res2))

    if not res2.get("ok"):
        msgs.append(asst("Vaya, justo se ha quedado sin hueco. ¿Quieres que mire otro día?"))
        msgs.append(usr(rng.choice(GRACIAS)))
        msgs.append(asst("Gracias a ti. Aquí estoy cuando quieras reservar."))
        return msgs, escenario

    cierre = rng.choice(["¿Algo más?", "¿Te ayudo con algo más?", "¿Necesitas algo más?"])
    msgs.append(asst("¡Listo! Te he reservado {} de {} {} a {}. Tu localizador es "
                     "{} y son {}. {}".format(
                         res2["recurso"], info["nombre"], humana_fecha(fecha, hoy),
                         hora_humana(hora), res2["localizador"], res2["precio"], cierre)))
    return msgs, escenario


def conv_crear(bk, hoy, rng):
    """Flujo principal: pedir datos -> disponibilidad -> confirmar -> crear."""
    slug = elegir_instalacion(rng)
    info = B.CATALOGO[slug]
    nombre_inst = info["nombre"]
    dur = rng.choice(info["duraciones"])
    franja = rng.choice([None, "manana", "tarde", "tarde", "noche"])

    frase_fecha, fecha = fecha_concreta(hoy, rng)
    frase_hora, hora = frase_hora_usuario(rng, franja)
    nombre = nombre_completo(rng)
    pide_personas = info["pregunta_personas"]
    num_personas = rng.randint(2, info["max_personas"]) if pide_personas else None

    # ¿Cuántos datos suelta el usuario en el primer mensaje?
    r = rng.random()
    if r < 0.15:
        conocidos = set()
    elif r < 0.45:
        conocidos = {"fecha"}
    elif r < 0.72:
        conocidos = {"fecha", "hora"}
    else:
        conocidos = {"fecha", "hora", "duracion"}

    # --- Primer mensaje del usuario ---
    apertura = "{} {}".format(rng.choice(VERBOS_RESERVA), rng.choice(TERMINOS[slug]))
    if "fecha" in conocidos:
        apertura += " para {}".format(frase_fecha)
    if "hora" in conocidos:
        apertura += " {}".format(frase_hora)
    if "duracion" in conocidos:
        apertura += ", {}".format(frase_duracion(dur))
    saludo = rng.choice(SALUDOS)
    primer = "{}, {}".format(saludo, apertura) if saludo else apertura

    msgs = [usr(primer)]
    meta = {"intencion": "crear_reserva", "instalacion": slug}

    # --- El asistente pide los datos que falten, de uno en uno ---
    preguntas = {
        "fecha": ["¿Para qué día lo quieres?", "¿Qué día te viene bien?"],
        "hora": ["¿A qué hora?", "¿A qué hora te vendría bien?"],
        "duracion": ["¿Una hora o una hora y media?" if 90 in info["duraciones"]
                     else "¿Cuánto rato lo quieres?", "¿Cuánto rato, una hora o más?"],
        "personas": ["¿Cuántos vais a ser?", "¿Cuántas personas sois?"],
        "nombre": ["¿A nombre de quién la pongo?", "¿A nombre de quién?"],
    }
    respuestas = {
        "fecha": frase_fecha,
        "hora": frase_hora,
        "duracion": frase_duracion(dur),
        "personas": rng.choice(["seremos {}".format(num_personas),
                                 "{}".format(num_personas),
                                 "{} personas".format(num_personas)]) if pide_personas else "",
        "nombre": nombre,
    }
    orden = ["fecha", "hora", "duracion"]
    if pide_personas:
        orden.append("personas")
    orden.append("nombre")

    primera_pregunta = True
    for slot in orden:
        if slot in conocidos:
            continue
        texto_pregunta = rng.choice(preguntas[slot])
        if primera_pregunta and slot != "nombre":
            texto_pregunta = "{} {}".format(rng.choice(["¡Hola! Claro.", "¡Claro!",
                              "Perfecto."]), texto_pregunta)
        msgs.append(asst(texto_pregunta))
        msgs.append(usr(respuestas[slot]))
        primera_pregunta = False

    # --- Consultar disponibilidad, confirmar y crear (lógica compartida) ---
    cuerpo, escenario = cerrar_reserva(bk, hoy, rng, slug, fecha, hora, dur,
                                       nombre, num_personas if pide_personas else None)
    meta["escenario"] = escenario
    return msgs + cuerpo, meta


def conv_disponibilidad(bk, hoy, rng):
    """Consulta de disponibilidad; a veces termina en reserva."""
    slug = elegir_instalacion(rng)
    info = B.CATALOGO[slug]
    nombre_inst = info["nombre"]
    dur = info["duraciones"][0]
    frase_fecha, fecha = fecha_concreta(hoy, rng)
    franja = rng.choice(["tarde", "manana", "noche", None])
    franja_txt = {"manana": " por la mañana", "tarde": " por la tarde",
                  "noche": " por la noche", None: ""}[franja]

    saludo = rng.choice(SALUDOS)
    pregunta = rng.choice([
        "¿hay {} libre {}{}?".format(rng.choice(TERMINOS[slug]), frase_fecha, franja_txt),
        "¿tenéis {} {}{}?".format(rng.choice(TERMINOS[slug]), frase_fecha, franja_txt),
        "¿qué disponibilidad hay de {} {}{}?".format(nombre_inst.lower(), frase_fecha, franja_txt),
    ])
    primer = "{}, {}".format(saludo, pregunta) if saludo else pregunta
    msgs = [usr(primer)]
    meta = {"intencion": "consultar_disponibilidad", "instalacion": slug}

    res = bk.consultar_disponibilidad(slug, fecha, franja=franja, duracion_min=dur)
    msgs.append(tool_call("consultar_disponibilidad",
                {"instalacion": slug, "fecha": fecha, "franja": franja,
                 "duracion_min": dur}))
    msgs.append(tool_result(res))

    opciones = res["alternativas"]
    if not opciones:
        msgs.append(asst("Pues {}{} lo tengo todo completo. ¿Quieres que mire "
                         "otro día u otra hora?".format(frase_fecha, franja_txt)))
        msgs.append(usr(rng.choice(GRACIAS)))
        msgs.append(asst("De nada. Aquí estoy si quieres reservar o consultar algo."))
        meta["escenario"] = "completo"
        return msgs, meta

    horas = [o["hora"] for o in opciones[:3]]
    horas_txt = ", ".join(hora_humana(h) for h in horas[:-1])
    horas_txt = (horas_txt + " o " + hora_humana(horas[-1])) if len(horas) > 1 else hora_humana(horas[0])
    msgs.append(asst("Sí, {}{} tengo hueco a {}. ¿Quieres que te reserve alguna?".format(
        frase_fecha, franja_txt, horas_txt)))

    if rng.random() < 0.55:
        # Encadena en reserva
        elegida = opciones[0]
        hora = elegida["hora"]
        nombre = nombre_completo(rng)
        msgs.append(usr(rng.choice(["sí, la de {}".format(hora_humana(hora)),
                                    "vale, a {}".format(hora_humana(hora))])))
        msgs.append(asst("Genial. ¿A nombre de quién la pongo?"))
        msgs.append(usr(nombre))
        args = {"instalacion": slug, "fecha": fecha, "hora_inicio": hora,
                "duracion_min": dur, "nombre": nombre}
        if info["pregunta_personas"]:
            args["num_personas"] = rng.randint(2, info["max_personas"])
        msgs.append(asst("Perfecto: {} {} a {}, a nombre de {}. ¿La reservo?".format(
            nombre_inst, humana_fecha(fecha, hoy), hora_humana(hora), nombre)))
        msgs.append(usr(rng.choice(SI)))
        res2 = bk.crear_reserva(**args)
        msgs.append(tool_call("crear_reserva", args))
        msgs.append(tool_result(res2))
        msgs.append(asst("¡Hecho! {} reservada, localizador {} y son {}. ¿Algo más?".format(
            res2["recurso"], res2["localizador"], res2["precio"])))
        meta["escenario"] = "deriva_en_reserva"
    else:
        msgs.append(usr(rng.choice(["de momento solo quería mirar, " + rng.choice(GRACIAS),
                                    "vale, me lo pienso y vuelvo, " + rng.choice(GRACIAS)])))
        msgs.append(asst("¡Claro! Cuando quieras reservar, aquí estoy."))
        meta["escenario"] = "solo_consulta"
    return msgs, meta


def _crear_reserva_previa(bk, hoy, rng):
    """Crea en el backend una reserva YA existente (para consultar/modificar/cancelar).

    Importante: probamos varios días hasta encontrar un hueco REALMENTE libre y
    comprobamos que la creación tuvo éxito; así nunca devolvemos algo sin
    localizador (que rompería las conversaciones de estado/cancelar/modificar).
    """
    slug = elegir_instalacion(rng)
    info = B.CATALOGO[slug]
    dur = rng.choice(info["duraciones"])
    nombre = nombre_completo(rng)

    intentos = [(slug, info, dur)]
    # Plan B por si la instalación elegida está muy llena: pádel (4 pistas) a 60 min.
    intentos.append(("padel", B.CATALOGO["padel"], 60))

    for s, inf, d in intentos:
        for extra in range(1, 30):
            fecha = (hoy + timedelta(days=extra)).isoformat()
            hue = bk.buscar_huecos(s, fecha, d, max_op=1)
            if not hue:
                continue
            hora = hue[0]["hora"]
            args = {"instalacion": s, "fecha": fecha, "hora_inicio": hora,
                    "duracion_min": d, "nombre": nombre}
            if inf["pregunta_personas"]:
                args["num_personas"] = rng.randint(2, inf["max_personas"])
            res = bk.crear_reserva(**args)
            if res.get("ok"):
                return {"slug": s, "nombre_inst": inf["nombre"], "fecha": fecha,
                        "hora": hora, "dur": d, "nombre": nombre,
                        "localizador": res["localizador"]}
    raise RuntimeError("No se pudo crear una reserva previa (no debería pasar).")


def conv_estado(bk, hoy, rng):
    """Consultar el estado de una reserva (por localizador o por nombre)."""
    r = _crear_reserva_previa(bk, hoy, rng)
    msgs = []
    meta = {"intencion": "consultar_reserva", "instalacion": r["slug"]}

    # A veces empieza con una pregunta fuera de tema y el asistente reconduce.
    if rng.random() < 0.35:
        off = rng.choice([
            ("oye, ¿sabes si mañana lloverá?", "Del tiempo no te puedo informar, lo siento."),
            ("¿qué tal va tu día?", "¡Muy bien, gracias!"),
        ])
        msgs.append(usr(off[0]))
        msgs.append(asst("{} En lo que sí te ayudo es con tus reservas: ¿quieres "
                         "reservar algo o consultar una reserva tuya?".format(off[1])))
        meta["escenario"] = "tras_fuera_de_dominio"
    else:
        meta["escenario"] = "directo"

    por_localizador = rng.random() < 0.5
    if por_localizador:
        msgs.append(usr(rng.choice([
            "quería consultar mi reserva, el localizador es {}".format(r["localizador"]),
            "¿me dices cómo está la reserva {}?".format(r["localizador"]),
        ])))
        res = bk.consultar_reserva(localizador=r["localizador"])
        msgs.append(tool_call("consultar_reserva", {"localizador": r["localizador"]}))
    else:
        msgs.append(usr(rng.choice([
            "¿en qué quedó mi reserva de {}?".format(r["nombre_inst"].lower()),
            "quería saber el estado de mi reserva",
        ])))
        msgs.append(asst("Claro. ¿Me das el localizador, o prefieres que la busque por tu nombre?"))
        msgs.append(usr("por nombre, {}".format(r["nombre"])))
        res = bk.consultar_reserva(nombre=r["nombre"])
        msgs.append(tool_call("consultar_reserva", {"nombre": r["nombre"]}))
    msgs.append(tool_result(res))

    msgs.append(asst("La tengo: {} en {} {} a {}, {}. Está {} y el localizador es {}. "
                     "¿Quieres cambiarla o cancelarla, o lo dejamos así?".format(
                         res["instalacion"].lower(), res["recurso"],
                         humana_fecha(res["fecha"], hoy), hora_humana(res["hora_inicio"]),
                         frase_duracion(res["duracion_min"]), res["estado"],
                         res["localizador"])))
    msgs.append(usr(rng.choice(["déjalo así, " + rng.choice(GRACIAS),
                                "nada más, " + rng.choice(GRACIAS)])))
    msgs.append(asst("¡Perfecto! Aquí estaré si quieres reservar o consultar algo más."))
    return msgs, meta


def conv_modificar(bk, hoy, rng):
    """Modificar una reserva existente (cambiar la hora)."""
    r = _crear_reserva_previa(bk, hoy, rng)
    msgs = [usr(rng.choice([
        "hola, quería cambiar la hora de mi reserva de {}".format(r["nombre_inst"].lower()),
        "necesito mover una reserva que tengo",
    ]))]
    meta = {"intencion": "modificar_reserva", "instalacion": r["slug"], "escenario": "cambio_hora"}

    msgs.append(asst("Claro. ¿Me das el localizador?"))
    msgs.append(usr(r["localizador"]))
    res = bk.consultar_reserva(localizador=r["localizador"])
    msgs.append(tool_call("consultar_reserva", {"localizador": r["localizador"]}))
    msgs.append(tool_result(res))
    msgs.append(asst("La tengo, ahora es {} a {}. ¿A qué hora la quieres mover?".format(
        humana_fecha(res["fecha"], hoy), hora_humana(res["hora_inicio"]))))

    # Nueva hora con disponibilidad real
    hue = bk.buscar_huecos(r["slug"], r["fecha"], r["dur"], max_op=5)
    opciones = [h["hora"] for h in hue if h["hora"] != r["hora"]]
    nueva = rng.choice(opciones) if opciones else r["hora"]
    msgs.append(usr("a {}".format(hora_humana(nueva))))
    msgs.append(asst("Perfecto. Te la cambio a {}. ¿Confirmo?".format(hora_humana(nueva))))
    msgs.append(usr(rng.choice(SI)))
    res2 = bk.modificar_reserva(r["localizador"], {"hora_inicio": nueva})
    msgs.append(tool_call("modificar_reserva",
                {"localizador": r["localizador"], "cambios": {"hora_inicio": nueva}}))
    msgs.append(tool_result(res2))
    msgs.append(asst("¡Hecho! Tu reserva {} queda a {}. ¿Algo más?".format(
        r["localizador"], hora_humana(nueva))))
    return msgs, meta


def conv_cancelar(bk, hoy, rng):
    """Cancelar una reserva existente (con confirmación)."""
    r = _crear_reserva_previa(bk, hoy, rng)
    por_nombre = rng.random() < 0.5
    msgs = [usr(rng.choice([
        "quería cancelar una reserva",
        "hola, necesito anular mi reserva de {}".format(r["nombre_inst"].lower()),
    ]))]
    meta = {"intencion": "cancelar_reserva", "instalacion": r["slug"],
            "escenario": "por_nombre" if por_nombre else "por_localizador"}

    if por_nombre:
        msgs.append(asst("Vaya, lo siento. ¿Me das el localizador o la busco por tu nombre?"))
        msgs.append(usr("búscala por mi nombre, {}".format(r["nombre"])))
        res = bk.consultar_reserva(nombre=r["nombre"])
        msgs.append(tool_call("consultar_reserva", {"nombre": r["nombre"]}))
    else:
        msgs.append(asst("De acuerdo. ¿Me das el localizador?"))
        msgs.append(usr(r["localizador"]))
        res = bk.consultar_reserva(localizador=r["localizador"])
        msgs.append(tool_call("consultar_reserva", {"localizador": r["localizador"]}))
    msgs.append(tool_result(res))

    msgs.append(asst("La tengo: {} {} a {}. ¿Te la cancelo?".format(
        res["instalacion"].lower(), humana_fecha(res["fecha"], hoy),
        hora_humana(res["hora_inicio"]))))
    msgs.append(usr(rng.choice(["sí, cancélala", "sí por favor", "eso es, cancélala"])))
    res2 = bk.cancelar_reserva(res["localizador"])
    msgs.append(tool_call("cancelar_reserva", {"localizador": res["localizador"]}))
    msgs.append(tool_result(res2))
    msgs.append(asst("Listo, he cancelado la reserva {}. ¿Necesitas algo más?".format(
        res["localizador"])))
    return msgs, meta


def conv_info(bk, hoy, rng):
    """Pregunta de información: se responde desde el system prompt y se reconduce."""
    reconduce = rng.choice([
        " ¿Quieres que te reserve algo o que mire una reserva tuya?",
        " ¿Te reservo alguna instalación?",
        " ¿Quieres reservar?",
    ])
    qa = [
        ("¿a qué hora abrís?", "Abrimos todos los días de ocho de la mañana a diez de la noche."),
        ("¿cuánto cuesta una pista de pádel?", "El pádel son 8 euros la hora, y si eres socio, 6."),
        ("¿qué precio tiene el tenis?", "El tenis son 10 euros la hora."),
        ("¿se puede pagar con tarjeta?", "Sí, puedes pagar en la instalación en efectivo o con tarjeta."),
        ("¿tenéis vestuarios?", "Sí, hay vestuarios con duchas."),
        ("¿hay parking?", "Sí, hay aparcamiento gratuito junto al centro."),
        ("¿alquiláis palas de pádel?", "Sí, las palas y las pelotas se alquilan en recepción."),
        ("¿abrís los domingos?", "Sí, abrimos todos los días, también findes y festivos."),
        ("¿cómo me hago socio?", "El alta de socio se tramita en recepción; los socios tienen descuento."),
    ]
    pregunta, respuesta = rng.choice(qa)
    saludo = rng.choice(SALUDOS)
    primer = "{}, {}".format(saludo, pregunta) if saludo else pregunta
    msgs = [usr(primer), asst(respuesta + reconduce)]
    if rng.random() < 0.4:
        msgs.append(usr(rng.choice(GRACIAS)))
        msgs.append(asst("¡A ti! Aquí estoy cuando quieras reservar."))
    return msgs, {"intencion": "info", "escenario": "faq"}


def conv_fuera(bk, hoy, rng):
    """Tema ajeno: reconocer con amabilidad y reconducir SIEMPRE al objetivo."""
    casos = [
        "¿qué tiempo va a hacer mañana?",
        "cuéntame un chiste",
        "¿quién ganó el partido de ayer?",
        "¿cuánto es 234 por 12?",
        "¿me recomiendas una serie?",
        "¿sabes cocinar una paella?",
        "¿qué opinas de la política?",
        "tradúceme 'hola' al inglés",
    ]
    pregunta = rng.choice(casos)
    saludo = rng.choice(SALUDOS)
    primer = "{}, {}".format(saludo, pregunta) if saludo else pregunta
    cortes = ["Uy, de eso no te puedo ayudar.", "Eso se me escapa, lo siento.",
              "Para eso no soy yo, la verdad."]
    msgs = [usr(primer),
            asst("{} Yo me encargo de las reservas del polideportivo: ¿quieres "
                 "reservar una instalación o consultar una reserva tuya?".format(rng.choice(cortes)))]
    if rng.random() < 0.5:
        msgs.append(usr(rng.choice(["ah, vale", "jaja vale", "vale, gracias"])))
        msgs.append(asst("¡Sin problema! Aquí estoy si lo necesitas."))
    return msgs, {"intencion": "fuera_de_dominio", "escenario": "off_topic"}


def _localizador_falso(bk, rng):
    """Genera un localizador con el formato correcto pero que NO existe."""
    alfabeto = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    while True:
        loc = "PM-" + "".join(rng.choice(alfabeto) for _ in range(4))
        if loc not in bk.reservas:
            return loc


def conv_fecha_ambigua(bk, hoy, rng):
    """CASO DIFÍCIL: el usuario da una fecha vaga; el asistente la concreta."""
    slug = elegir_instalacion(rng)
    info = B.CATALOGO[slug]
    dur = info["duraciones"][0]
    nombre = nombre_completo(rng)
    vago = rng.choice(["el finde", "la semana que viene", "un día de estos", "entre semana"])
    saludo = rng.choice(SALUDOS)
    ap = "{} {} {}".format(rng.choice(VERBOS_RESERVA), rng.choice(TERMINOS[slug]), vago)
    msgs = [usr("{}, {}".format(saludo, ap) if saludo else ap)]
    meta = {"intencion": "crear_reserva", "instalacion": slug, "escenario": "fecha_ambigua"}

    if vago == "el finde":
        msgs.append(asst("¡Claro! ¿Te viene mejor el sábado o el domingo?"))
        if rng.random() < 0.5:
            fecha, dia = proximo_dia_semana(hoy, 5).isoformat(), "el sábado"
        else:
            fecha, dia = proximo_dia_semana(hoy, 6).isoformat(), "el domingo"
        msgs.append(usr(dia))
    else:
        msgs.append(asst("¡Claro! ¿Qué día en concreto te viene bien?"))
        frase_f, fecha = fecha_concreta(hoy, rng)
        msgs.append(usr(frase_f))

    frase_h, hora = frase_hora_usuario(rng)
    msgs.append(asst("Perfecto. ¿A qué hora?"))
    msgs.append(usr(frase_h))
    msgs.append(asst("¿A nombre de quién la pongo?"))
    msgs.append(usr(nombre))
    num = rng.randint(2, info["max_personas"]) if info["pregunta_personas"] else None
    cuerpo, _ = cerrar_reserva(bk, hoy, rng, slug, fecha, hora, dur, nombre, num)
    return msgs + cuerpo, meta


def conv_fuera_horario(bk, hoy, rng):
    """CASO DIFÍCIL: piden una hora fuera del horario (8-22); el asistente lo corrige."""
    slug = elegir_instalacion(rng)
    info = B.CATALOGO[slug]
    dur = info["duraciones"][0]
    nombre = nombre_completo(rng)
    frase_f, fecha = fecha_concreta(hoy, rng)
    _, txt = rng.choice([(7, "a las siete de la mañana"),
                         (23, "a las once de la noche"),
                         (22, "a las diez de la noche")])
    saludo = rng.choice(SALUDOS)
    ap = "{} {} para {} {}".format(rng.choice(VERBOS_RESERVA),
                                   rng.choice(TERMINOS[slug]), frase_f, txt)
    msgs = [usr("{}, {}".format(saludo, ap) if saludo else ap)]
    meta = {"intencion": "crear_reserva", "instalacion": slug, "escenario": "fuera_de_horario"}
    msgs.append(asst("Uy, el centro abre de ocho de la mañana a diez de la noche, así "
                     "que a esa hora no puedo. ¿Te viene bien alguna hora dentro de ese horario?"))
    frase_h, hora = frase_hora_usuario(rng, rng.choice(["manana", "tarde"]))
    msgs.append(usr(frase_h))
    msgs.append(asst("Genial. ¿A nombre de quién?"))
    msgs.append(usr(nombre))
    num = rng.randint(2, info["max_personas"]) if info["pregunta_personas"] else None
    cuerpo, _ = cerrar_reserva(bk, hoy, rng, slug, fecha, hora, dur, nombre, num)
    return msgs + cuerpo, meta


def conv_duracion_invalida(bk, hoy, rng):
    """CASO DIFÍCIL: piden una duración no permitida; el asistente ofrece las válidas."""
    slug = rng.choice(["padel", "tenis", "futbol_sala", "futbol7", "baloncesto",
                       "fronton", "tatami"])
    info = B.CATALOGO[slug]
    nombre = nombre_completo(rng)
    frase_f, fecha = fecha_concreta(hoy, rng)
    frase_h, hora = frase_hora_usuario(rng)
    invalida = rng.choice(["dos horas", "tres horas", "media hora"])
    saludo = rng.choice(SALUDOS)
    ap = "{} {} para {} {}, {}".format(rng.choice(VERBOS_RESERVA),
                                       rng.choice(TERMINOS[slug]), frase_f, frase_h, invalida)
    msgs = [usr("{}, {}".format(saludo, ap) if saludo else ap)]
    meta = {"intencion": "crear_reserva", "instalacion": slug, "escenario": "duracion_invalida"}
    opciones_txt = " o ".join(frase_duracion(d) for d in info["duraciones"])
    msgs.append(asst("Para {} las reservas son de {}, no puedo ponerte {}. "
                     "¿Cuál prefieres?".format(info["nombre"].lower(), opciones_txt, invalida)))
    dur = rng.choice(info["duraciones"])
    msgs.append(usr(frase_duracion(dur)))
    msgs.append(asst("Perfecto. ¿A nombre de quién?"))
    msgs.append(usr(nombre))
    num = rng.randint(2, info["max_personas"]) if info["pregunta_personas"] else None
    cuerpo, _ = cerrar_reserva(bk, hoy, rng, slug, fecha, hora, dur, nombre, num)
    return msgs + cuerpo, meta


def conv_cambio_opinion(bk, hoy, rng):
    """CASO DIFÍCIL: el usuario cambia de idea (de hora) justo antes de confirmar."""
    slug = elegir_instalacion(rng)
    info = B.CATALOGO[slug]
    dur = info["duraciones"][0]
    nombre = nombre_completo(rng)
    frase_f, fecha = fecha_concreta(hoy, rng)
    horas = [h["hora"] for h in bk.buscar_huecos(slug, fecha, dur, max_op=6)]

    if len(horas) < 2:
        # Sin dos huecos libres no podemos escenificar el cambio: reserva normal.
        frase_h, hora = frase_hora_usuario(rng)
        msgs = [usr("{} {} para {} a {}".format(rng.choice(VERBOS_RESERVA),
                    rng.choice(TERMINOS[slug]), frase_f, frase_h))]
        msgs.append(asst("¡Claro! ¿A nombre de quién?"))
        msgs.append(usr(nombre))
        num = rng.randint(2, info["max_personas"]) if info["pregunta_personas"] else None
        cuerpo, _ = cerrar_reserva(bk, hoy, rng, slug, fecha, hora, dur, nombre, num)
        return msgs + cuerpo, {"intencion": "crear_reserva", "instalacion": slug,
                               "escenario": "directo"}

    h1, h2 = horas[0], horas[1]
    saludo = rng.choice(SALUDOS)
    ap = "{} {} para {} a {}".format(rng.choice(VERBOS_RESERVA),
                                     rng.choice(TERMINOS[slug]), frase_f, hora_humana(h1))
    msgs = [usr("{}, {}".format(saludo, ap) if saludo else ap)]
    meta = {"intencion": "crear_reserva", "instalacion": slug, "escenario": "cambio_de_opinion"}
    msgs.append(asst("¡Claro! ¿A nombre de quién?"))
    msgs.append(usr(nombre))
    msgs.append(asst("Te confirmo: {} {} a {}, {}, a nombre de {}. ¿La reservo?".format(
        info["nombre"], humana_fecha(fecha, hoy), hora_humana(h1), frase_duracion(dur), nombre)))
    msgs.append(usr(rng.choice(["uy espera, mejor a {}".format(hora_humana(h2)),
                                "perdona, cámbiala a {}".format(hora_humana(h2))])))
    msgs.append(asst("¡Sin problema! Lo cambio a {}.".format(hora_humana(h2))))
    res = bk.consultar_disponibilidad(slug, fecha, hora_inicio=h2, duracion_min=dur)
    msgs.append(tool_call("consultar_disponibilidad",
                {"instalacion": slug, "fecha": fecha, "hora_inicio": h2, "duracion_min": dur}))
    msgs.append(tool_result(res))
    msgs.append(asst("Confirmo entonces: {} {} a {}, a nombre de {}. ¿Reservo?".format(
        info["nombre"], humana_fecha(fecha, hoy), hora_humana(h2), nombre)))
    msgs.append(usr(rng.choice(SI)))
    args = {"instalacion": slug, "fecha": fecha, "hora_inicio": h2,
            "duracion_min": dur, "nombre": nombre}
    if info["pregunta_personas"]:
        args["num_personas"] = rng.randint(2, info["max_personas"])
    res2 = bk.crear_reserva(**args)
    msgs.append(tool_call("crear_reserva", args))
    msgs.append(tool_result(res2))
    msgs.append(asst("¡Listo! {} reservada {} a {}, localizador {} y son {}. ¿Algo más?".format(
        res2["recurso"], humana_fecha(fecha, hoy), hora_humana(h2),
        res2["localizador"], res2["precio"])))
    return msgs, meta


def conv_localizador_inexistente(bk, hoy, rng):
    """CASO DIFÍCIL: el localizador que da el usuario no existe; se busca por nombre."""
    r = _crear_reserva_previa(bk, hoy, rng)
    falso = _localizador_falso(bk, rng)
    msgs = [usr(rng.choice([
        "hola, quería consultar mi reserva, el localizador es {}".format(falso),
        "¿me dices cómo está la reserva {}?".format(falso),
    ]))]
    meta = {"intencion": "consultar_reserva", "instalacion": r["slug"],
            "escenario": "localizador_inexistente"}
    res = bk.consultar_reserva(localizador=falso)
    msgs.append(tool_call("consultar_reserva", {"localizador": falso}))
    msgs.append(tool_result(res))
    msgs.append(asst("Pues con ese localizador no me aparece ninguna reserva. "
                     "¿Lo revisas, o prefieres que la busque por tu nombre?"))
    msgs.append(usr("búscala por mi nombre, {}".format(r["nombre"])))
    res2 = bk.consultar_reserva(nombre=r["nombre"])
    msgs.append(tool_call("consultar_reserva", {"nombre": r["nombre"]}))
    msgs.append(tool_result(res2))
    msgs.append(asst("¡Ahora sí! La tengo: {} {} a {}, localizador {}. "
                     "¿Quieres hacer algo con ella?".format(
                         res2["instalacion"].lower(), humana_fecha(res2["fecha"], hoy),
                         hora_humana(res2["hora_inicio"]), res2["localizador"])))
    msgs.append(usr(rng.choice(["no, era solo por confirmar, " + rng.choice(GRACIAS),
                                "nada más, " + rng.choice(GRACIAS)])))
    msgs.append(asst("¡Perfecto! Aquí estoy para lo que necesites."))
    return msgs, meta


# Reparto de intenciones (debe sumar 100). Coincide con ESQUEMA.md §5.
INTENCIONES = [
    (conv_crear, 30),
    (conv_disponibilidad, 12),
    (conv_estado, 13),
    (conv_modificar, 7),
    (conv_cancelar, 6),
    (conv_info, 8),
    (conv_fuera, 7),
    # --- Casos difíciles (robustez ante "preguntas raras") ---
    (conv_fecha_ambigua, 5),
    (conv_fuera_horario, 4),
    (conv_duracion_invalida, 3),
    (conv_cambio_opinion, 3),
    (conv_localizador_inexistente, 2),
]


# ===========================================================================
# 5. ENSAMBLAJE DE UNA CONVERSACIÓN COMPLETA
# ===========================================================================

def generar_conversacion(indice, semilla, base):
    """Crea una conversación: elige escenario, monta su mundo y la 'actúa'."""
    rng = random.Random(semilla * 1_000_003 + indice)
    hoy = base + timedelta(days=rng.randint(0, 120))
    bk = B.Backend(hoy=hoy.isoformat(), seed=semilla * 7919 + indice)

    constructores = [c for c, _ in INTENCIONES]
    pesos = [p for _, p in INTENCIONES]
    constructor = rng.choices(constructores, weights=pesos, k=1)[0]

    cuerpo, meta = constructor(bk, hoy, rng)
    mensajes = [{"role": "system", "content": B.system_prompt(hoy.isoformat())}] + cuerpo
    return {"messages": mensajes, "meta": meta}


# ===========================================================================
# 6. UTILIDADES DE SALIDA (muestra legible y escritura JSONL)
# ===========================================================================

def imprimir_legible(conv, n):
    print("\n" + "=" * 74)
    print("CONVERSACIÓN {}  ·  intención: {}  ·  escenario: {}".format(
        n, conv["meta"].get("intencion"), conv["meta"].get("escenario", "-")))
    print("=" * 74)
    for m in conv["messages"]:
        if m["role"] == "system":
            print("[SYSTEM]   (system prompt — Fecha actual incluida)")
            continue
        etiqueta = {"user": "USUARIO  ", "assistant": "ASISTENTE", "tool": "TOOL     "}[m["role"]]
        contenido = m["content"]
        if "\n" in contenido:
            print("{} | {}".format(etiqueta, contenido.replace("\n", "\n           | ")))
        else:
            print("{} | {}".format(etiqueta, contenido))


def estadisticas(convs):
    from collections import Counter
    intenciones = Counter(c["meta"]["intencion"] for c in convs)
    turnos = [len([m for m in c["messages"] if m["role"] != "system"]) for c in convs]
    llamadas = sum(1 for c in convs for m in c["messages"]
                   if m["role"] == "assistant" and m["content"].startswith("```tool_call"))
    print("\n--- ESTADÍSTICAS ---")
    print("Total conversaciones : {}".format(len(convs)))
    print("Turnos por conv (medio): {:.1f}".format(sum(turnos) / len(turnos)))
    print("Llamadas a herramienta : {} (media {:.2f}/conv)".format(llamadas, llamadas / len(convs)))
    print("Reparto de intenciones:")
    for nombre, cuenta in intenciones.most_common():
        print("  {:24s} {:4d}  ({:.0f}%)".format(nombre, cuenta, 100 * cuenta / len(convs)))


def escribir_jsonl(ruta, convs):
    with open(ruta, "w", encoding="utf-8") as f:
        for c in convs:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


# ===========================================================================
# 7. PUNTO DE ENTRADA
# ===========================================================================

def main():
    ap = argparse.ArgumentParser(description="Generador del dataset de reservas")
    ap.add_argument("--n", type=int, default=1200, help="nº de conversaciones")
    ap.add_argument("--semilla", type=int, default=42, help="semilla (reproducibilidad)")
    ap.add_argument("--base", default="2026-09-01", help="fecha base (YYYY-MM-DD)")
    ap.add_argument("--salida", default="dataset.jsonl", help="fichero de salida")
    ap.add_argument("--val", type=float, default=0.1, help="fracción de validación")
    ap.add_argument("--muestra", type=int, default=0,
                    help="si >0, solo imprime N conversaciones legibles y no escribe nada")
    args = ap.parse_args()

    base = date.fromisoformat(args.base)

    if args.muestra:
        for i in range(args.muestra):
            imprimir_legible(generar_conversacion(i, args.semilla, base), i + 1)
        return

    convs = [generar_conversacion(i, args.semilla, base) for i in range(args.n)]
    estadisticas(convs)

    # Barajar de forma reproducible y separar train/val.
    rng = random.Random(args.semilla)
    rng.shuffle(convs)
    n_val = int(len(convs) * args.val)
    val, train = convs[:n_val], convs[n_val:]

    escribir_jsonl(args.salida, convs)
    base_nombre = args.salida.rsplit(".", 1)[0]
    escribir_jsonl(base_nombre + "_train.jsonl", train)
    escribir_jsonl(base_nombre + "_val.jsonl", val)
    print("\nEscritos:")
    print("  {}  ({} conversaciones)".format(args.salida, len(convs)))
    print("  {}_train.jsonl  ({})".format(base_nombre, len(train)))
    print("  {}_val.jsonl  ({})".format(base_nombre, len(val)))


if __name__ == "__main__":
    main()
