# Capa 1 del embudo AI-first · Ingesta de datos en GCP

Serie de cuadernos de Google Colab para aprender, desde cero, la **capa de ingesta de datos** en Google Cloud Platform.

## Cuadernos

| # | Cuaderno | Abrir en Colab |
|---|----------|----------------|
| 0 | Fundamentos y setup | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/noelserdna/capa1-ingesta-colab/blob/main/00_fundamentos_setup.ipynb) |
| 1 | Ingesta batch: API pública → BigQuery | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/noelserdna/capa1-ingesta-colab/blob/main/01_batch_api_a_bigquery.ipynb) |

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
