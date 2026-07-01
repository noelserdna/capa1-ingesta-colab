# 💬 Demo web · Asistente de reservas (chat + Node + Ollama)

Chat web para hablar con el **Gemma 4 E2B fine-tuneado**. El servidor Node ejecuta
el **bucle de herramientas**: tu mensaje → el modelo → si pide una `tool_call`, la
ejecuta contra `backend_sim.js` (el backend simulado) → le devuelve el resultado →
repite hasta responderte. El panel derecho muestra la **"base de datos" de reservas
actualizándose en vivo**.

```
demo/
├── server.js          # Express: sirve el chat + API + bucle de herramientas (llama a Ollama)
├── backend_sim.js     # backend simulado en JS (catálogo, agenda, reservas, las 5 herramientas)
├── package.json
└── public/            # el chat (HTML + CSS + JS vanilla)
    ├── index.html · styles.css · app.js
```

---

## Requisitos

- **Node.js 18+** (usa `fetch` nativo).
- **[Ollama](https://ollama.com)** corriendo en local (sirve el modelo por HTTP).
  Para el **modelo fine-tuneado** necesitas **Ollama 0.30+** (el soporte de adapters
  LoRA para Gemma 4 llegó en la 0.30; en versiones previas da `loras are not yet implemented`).

## 1. Prepara el modelo en Ollama

**Opción A — probar YA con el modelo base** (rápido, sin fine-tuning):
```bash
ollama pull gemma4:e2b
export MODEL=gemma4:e2b
```
El base + el *system prompt* ya sigue bastante bien el protocolo de herramientas.

**Opción B — usar TU modelo fine-tuneado** (¡ya listo!): el adapter LoRA en GGUF ya
está en `../deploy/reservas-lora-f16.gguf` (48 MB). Solo crea el modelo en Ollama
(el `Modelfile` hace `FROM gemma4:e2b` + `ADAPTER`):
```bash
ollama pull gemma4:e2b
ollama create reservas -f ../deploy/Modelfile
export MODEL=reservas
```

## 2. Arranca la demo
```bash
cd demo
npm install
npm start          # o: node server.js
```
Abre **http://localhost:3000**.

---

## Configuración (variables de entorno)

| Variable | Def. | Qué es |
|----------|------|--------|
| `MODEL` | `reservas` | nombre del modelo en Ollama (`gemma4:e2b` para el base) |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | dónde escucha Ollama |
| `PORT` | `3000` | puerto de la demo |

Ejemplo: `MODEL=gemma4:e2b PORT=8080 node server.js`

---

## Cómo funciona (el bucle de herramientas)

1. El navegador manda tu mensaje a `POST /api/chat`.
2. `server.js` construye el prompt con **la misma plantilla del entrenamiento** y llama
   a Ollama por `/api/generate` con `raw: true` (así el modelo emite `\`\`\`tool_call` y no
   se mezcla con la plantilla nativa de Gemma).
3. Si la respuesta trae un bloque ` ```tool_call `, el servidor lo parsea y ejecuta
   la función correspondiente de `backend_sim.js` (p. ej. `consultar_disponibilidad`).
4. El resultado se devuelve al modelo como un turno más y se repite hasta que el
   modelo responde en lenguaje natural (sin `tool_call`).
5. La respuesta y el estado de las reservas vuelven al navegador.

> Es exactamente el patrón que usarías en producción: solo tendrías que sustituir
> `backend_sim.js` por tu backend real (mismas 5 funciones).

## Notas

- Al abrir la demo se **siembran** un par de reservas de ejemplo (Marta Ruiz, Carlos
  Gil) para poder probar *consultar/modificar/cancelar* al instante.
- "Reiniciar" borra la conversación y el estado del backend.
- Si ves `⚠️ No pude conectar con Ollama`, asegúrate de que Ollama está arrancado
  (`ollama serve`) y de que `MODEL` existe (`ollama list`).
