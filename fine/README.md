# 🏟️ Fine-tuning de Gemma 4 E2B — Asistente de reservas de instalaciones

Proyecto didáctico para **especializar un modelo Gemma 4 E2B** y convertirlo en el
asistente de reservas de un polideportivo. El modelo **conversa**, **llama a
herramientas** para consultar/crear/modificar/cancelar reservas, y **reconduce
siempre** hacia el objetivo: que el usuario reserve o conozca el estado de su reserva.

> **Solo texto** por ahora (la parte de voz se añadiría después con STT/TTS).
> El entrenamiento se hace en **Google Colab** (GPU T4 gratis) y, de momento, el
> modelo también se **prueba dentro del propio Colab**.

---

## La idea en 30 segundos

| | |
|---|---|
| **Modelo** | Gemma 4 E2B (2,3B efectivos, multimodal, 128K contexto) |
| **Técnica** | QLoRA (LoRA + base en 4 bits) con [Unsloth](https://unsloth.ai) |
| **Enfoque** | El modelo llama a **herramientas**; un **backend simulado** las responde |
| **Datos** | 1.200 conversaciones **sintéticas** en español, 100% reproducibles |
| **Dónde** | Entrenar e inferir en **Colab**; servidor (Ollama) queda para el futuro |

Por qué "con herramientas": para *conocer el estado de una reserva* o *ver
disponibilidad* hay que **mirar datos**. El modelo no se los inventa: pide una
herramienta (`consultar_disponibilidad`, `crear_reserva`…) y otra parte del sistema
(aquí, un backend simulado; mañana, tu base de datos) le devuelve el resultado.

---

## Estructura

```
fine/
├── data/
│   ├── ESQUEMA.md            # CONTRATO: roles, 5 herramientas, system prompt, reparto
│   ├── backend_sim.py        # backend simulado (catálogo + agenda determinista + reservas)
│   ├── generar_dataset.py    # generador del dataset (parametrizable y comentado)
│   ├── dataset.jsonl         # 1.200 conversaciones
│   ├── dataset_train.jsonl   # 1.080 (entrenamiento)
│   └── dataset_val.jsonl     # 120 (validación)
├── notebooks/
│   └── finetune_gemma4_reservas.ipynb   # Colab: instalar→cargar→entrenar→PROBAR→guardar
├── deploy/                   # FUTURO (servidor con Ollama)
│   ├── Modelfile
│   ├── system_prompt.txt
│   └── DESPLIEGUE.md
└── README.md
```

---

## Cómo usarlo, paso a paso

### 1. (Opcional) Regenerar o ampliar los datos — en local
```bash
cd fine/data
python3 generar_dataset.py --n 1200            # genera dataset(+train/val)
python3 generar_dataset.py --muestra 8         # solo imprime 8 conversaciones legibles
python3 backend_sim.py                         # demo del backend simulado
```
El dataset ya está generado en el repo; solo necesitas esto si cambias el catálogo
o quieres más ejemplos (`--n 3000`).

### 2. Entrenar — en Google Colab
Abre `notebooks/finetune_gemma4_reservas.ipynb` en Colab, pon **Entorno → GPU (T4)**
y ejecuta las celdas en orden. El notebook:
1. instala Unsloth y carga Gemma 4 E2B en 4 bits,
2. añade adaptadores LoRA,
3. entrena (~30-45 min),
4. **prueba el modelo con el bucle de herramientas** usando `backend_sim`,
5. guarda el **adapter LoRA en tu Google Drive** (las sesiones de Colab se borran).

### 3. Desplegar — FUTURO
Cuando montes tu servidor de 12 GB, exporta a GGUF (Paso 10 del notebook) y sigue
[`deploy/DESPLIEGUE.md`](deploy/DESPLIEGUE.md): Ollama + tu backend real haciendo
el mismo bucle de herramientas.

---

## El diseño de los datos (lo importante)

Todo el contrato está en [`data/ESQUEMA.md`](data/ESQUEMA.md). En resumen:

- **Formato**: JSONL, una conversación por línea, con roles `system`, `user`,
  `assistant`, `tool`.
- **Herramientas**: el asistente escribe un bloque ` ```tool_call ` con
  `{"tool": ..., "args": {...}}`; el resultado vuelve en un turno `tool`.
- **Confirma** antes de crear/modificar/cancelar. **Nunca** enseña el JSON al usuario.
- **Casos cubiertos**: reservar, ver disponibilidad, estado, modificar, cancelar,
  FAQs, y casos difíciles (fecha ambigua, fuera de horario, duración inválida,
  cambio de opinión, localizador inexistente, off-topic con reconducción).
- **Reproducible**: con la misma `--semilla` salen exactamente los mismos datos.
  El backend es **determinista** (la ocupación se calcula con un hash estable).

---

## Notas de aprendizaje

- **LoRA / QLoRA**: en vez de reentrenar miles de millones de pesos, entrenamos
  unas matrices pequeñas (LoRA); con la base en 4 bits (QLoRA) cabe en una T4.
- **`train_on_responses_only`**: el modelo aprende solo de los turnos del
  asistente, no de copiar al usuario.
- **Plantilla de chat propia**: definimos una plantilla Jinja que entiende el rol
  `tool` (Gemma de serie solo tiene `user`/`model`).

## ⚠️ A verificar en la primera ejecución
Estas dos líneas se escribieron según la documentación de Unsloth para Gemma 4
pero **no se han podido probar fuera de Colab**:
1. el `model_name` exacto (`unsloth/gemma-4-E2B-it`),
2. el export a GGUF de Gemma 4 (por eso va con `try/except` y plan B `merged_16bit`).
