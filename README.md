# Capa 1 del embudo AI-first · Ingesta de datos en GCP

Serie de cuadernos de Google Colab para aprender, desde cero, la **capa de ingesta de datos** en Google Cloud Platform.

## Cuadernos

| # | Cuaderno | Abrir en Colab |
|---|----------|----------------|
| 0.0 | Panorama de la Capa 1 (clase de 90 min: las 7 tecnologías de ingesta) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/noelserdna/capa1-ingesta-colab/blob/main/00_0_panorama_capa1_ingesta.ipynb) |
| 0 | Fundamentos y setup | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/noelserdna/capa1-ingesta-colab/blob/main/00_fundamentos_setup.ipynb) |
| 1 | Ingesta batch: API pública → BigQuery | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/noelserdna/capa1-ingesta-colab/blob/main/01_batch_api_a_bigquery.ipynb) |

## Qué cubre el Notebook 0.0 (Panorama)

Clase magistral de 90 min que da el **mapa de toda la Capa 1** antes de bajar al detalle práctico. Caso conductor **InnovaCo**, stack didáctico Notion + Google Workspace + Telegram + Neon Postgres.

- Los **4 modos de ingesta**: batch, streaming, CDC y event-driven.
- Las **7 tecnologías** y cuándo usar (y no usar) cada una: **Application Integration**, **Workflows**, **Pub/Sub**, **Eventarc**, **Datastream**, **Storage Transfer Service** y **Cortex Framework**.
- Patrón de trabajo AI-first: *arquitectura → prompt → LLM genera YAML/código → revisión → `gcloud`*.
- Por bloque: concepto, anatomía, prompt de ejemplo, YAML/código generado, comandos `gcloud`, trampas y ejercicio mental.
- Trampas transversales, biblioteca de prompts reutilizables y guía de setup del stack en 30 min.
- Incluye celdas Python ejecutables (mapa mental, recomendador de tecnología, plantilla de prompts) que corren sin ningún setup.

## Qué cubre el Notebook 0

- Qué es la nube, GCP y Colab (con analogías).
- Python mínimo imprescindible (variables, diccionarios, listas, funciones).
- Qué es una API REST y qué es JSON, en vivo.
- Autenticación y por qué no se escriben contraseñas en el código.
- Conectar Colab con tu proyecto de Google Cloud.
- Consultar un dataset público de BigQuery.
- Los 4 modos de ingesta que organizan la serie.

**Tiempo estimado:** 60-90 min.

## Qué cubre el Notebook 1

Tu **primera ingesta de datos real**: traer información de una fuente externa y dejarla en BigQuery, lista para que una IA razone sobre ella.

- Qué es la **ingesta batch** (por lotes) y cuándo es el modo adecuado.
- Llamar a una **API pública** (clima, sin clave) y entender su respuesta JSON.
- Qué es la **paginación** y cómo recorrer datos página a página.
- **Transformar** datos crudos a un **esquema canónico** limpio con pandas.
- Escribir en BigQuery con **MERGE** para una ingesta **idempotente** (ejecutarla dos veces no duplica).
- Hacer ingesta **incremental** (traer solo lo nuevo).
- Desplegar en producción con un **prompt para Claude Code + gcloud**.

**Requisito:** Notebook 0 completado (entorno en verde). **Tiempo estimado:** ~60 min.

## Uso

Abre cualquier cuaderno con su badge **Open in Colab** o clónalo:

```bash
git clone https://github.com/noelserdna/capa1-ingesta-colab.git
```
