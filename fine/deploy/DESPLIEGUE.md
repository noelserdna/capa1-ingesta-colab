# Despliegue en servidor (FUTURO)

> Esta carpeta es para **cuando dejes Colab** y montes el asistente en tu servidor
> de 12 GB. Mientras tanto, el modelo se usa dentro del propio notebook (Paso 8).

El plan: servir el modelo fine-tuneado con **Ollama** (CPU o GPU) usando el
fichero **GGUF** que genera el notebook (Paso 10), y que **tu aplicación** haga el
bucle de herramientas contra tu base de datos real.

---

## 1. Requisitos del servidor

- **Ollama** instalado: `curl -fsSL https://ollama.com/install.sh | sh`
- El fichero `gemma4-e2b-reservas-Q4_K_M.gguf` (del notebook) copiado aquí.
- RAM: con `Q4_K_M` (~3-4 GB) + `num_ctx 8192`, entra de sobra en 12 GB.

### Consejos de memoria (12 GB)
- **Cuantización**: `Q4_K_M` es el equilibrio bueno. Si vas muy justo, `Q4_0`.
- **`num_ctx`**: no necesitas los 128K. Con **8192** sobra para estas
  conversaciones y el consumo de RAM se mantiene bajo.
- **`OLLAMA_KEEP_ALIVE`**: ponlo alto (p. ej. `30m`) para que el modelo no se
  descargue de memoria entre peticiones y la primera respuesta no sea lenta.

---

## 2. Crear y arrancar el modelo

```bash
# En la carpeta donde estén el .gguf y el Modelfile:
ollama create reservas -f Modelfile
ollama run reservas        # prueba rápida por consola
```

---

## 3. El bucle de herramientas (lo más importante)

El modelo **no** accede solo a tu base de datos: cuando necesita datos, escribe un
bloque ` ```tool_call ` y **tu aplicación** debe:

1. detectar ese bloque y parsear el JSON `{"tool": ..., "args": {...}}`,
2. ejecutar esa función contra tu **backend real** (reemplazando `backend_sim`),
3. devolver el resultado como un turno con rol `tool`,
4. volver a llamar al modelo hasta que responda al usuario (sin `tool_call`).

Es exactamente el bucle del **Paso 8 del notebook**. Aquí tienes un cliente Python
mínimo que habla con Ollama y usa `backend_sim` como backend (cámbialo por el tuyo):

```python
# cliente_ollama.py
import re, json, datetime as dt
import requests
import backend_sim as B          # <-- en producción, tu backend REAL

OLLAMA = "http://localhost:11434/api/chat"
MODELO = "reservas"

def extraer_tool_call(texto):
    m = re.search(r"```tool_call\s*(\{.*?\})\s*```", texto, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

def turno_modelo(messages):
    # Ollama aplica la plantilla del modelo; el rol "tool" lo mandamos como user.
    payload = {"model": MODELO, "messages": messages, "stream": False,
               "options": {"temperature": 0.3}}
    r = requests.post(OLLAMA, json=payload, timeout=120)
    return r.json()["message"]["content"].strip()

def responder(backend, messages, texto_usuario):
    messages.append({"role": "user", "content": texto_usuario})
    for _ in range(6):
        salida = turno_modelo(messages)
        messages.append({"role": "assistant", "content": salida})
        tc = extraer_tool_call(salida)
        if tc is None:
            return salida                       # respuesta para el usuario
        resultado = backend.ejecutar(tc["tool"], tc.get("args", {}))
        # El resultado se devuelve como un turno "tool" (Ollama lo trata como user):
        messages.append({"role": "tool", "content": json.dumps(resultado, ensure_ascii=False)})
    return "Lo siento, no he podido completar la operación."

if __name__ == "__main__":
    hoy = dt.date.today().isoformat()
    backend = B.Backend(hoy=hoy, seed=0)
    # IMPORTANTE: el system prompt lleva la fecha REAL de hoy.
    messages = [{"role": "system", "content": B.system_prompt(hoy)}]
    print(responder(backend, messages, "Hola, quiero reservar pádel para mañana a las 7"))
```

> **Nota sobre el rol `tool`:** Ollama no tiene un rol `tool` nativo en su
> plantilla de Gemma; lo más seguro es mandar el resultado como un turno de
> `user` con el JSON (o con el formato ` ```tool_result `). Verifica que la
> plantilla embebida en tu GGUF coincide con la del entrenamiento (la plantilla
> propia del Paso 5). Si no, construye el prompt tú mismo y usa `/api/generate`.

---

## 4. La fecha de hoy

El system prompt incluye `Fecha actual: ...` para que el modelo resuelva "mañana",
"el sábado", etc. **Pon siempre la fecha real del día** al construir el system
prompt en tu aplicación (como en el `cliente_ollama.py` de arriba). Por eso el
`Modelfile` lleva el marcador `{{FECHA_ACTUAL}}`: no dejes ese SYSTEM fijo en
producción salvo que regeneres el Modelfile cada día.

---

## 5. Checklist de paso a producción

- [ ] Sustituir `backend_sim` por tu backend real (misma firma de las 5 funciones).
- [ ] Validar que la plantilla de chat del GGUF = la del entrenamiento.
- [ ] Inyectar la fecha real en el system prompt por conversación.
- [ ] Logs de las `tool_call` para auditar qué pide el modelo.
- [ ] Pruebas con los casos difíciles (localizador inexistente, fuera de horario…).
