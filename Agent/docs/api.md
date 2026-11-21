# API privada del agente

El navegador consume el Backend, nunca este servicio. Local: puerto 8001.
Las rutas /v1/* requieren X-API-Key si AGENT_API_KEY está configurada.
Modal exige además Modal-Key y Modal-Secret, solo conocidos por el Backend.

## Catálogo inmutable

1. GET /v1/catalog/snapshots/{digest} informa available.
2. Si falta: POST /v1/catalog/snapshots recibe {"digest":"sha256","snapshot":{...}}.
3. El digest es SHA-256 del JSON UTF-8 canónico: ensure_ascii=False,
   sort_keys=True, separators=(",",":"). Se verifica antes de escribir.
4. La consulta incluye catalog_digest; un digest inexistente devuelve 409,
   nunca datos de ejemplo. Límite de carga: 50 MB.

El Backend reutiliza su snapshot público cacheado y ETag. Solo transfiere el
catálogo cuando falta en el worker; no necesita túnel hacia PostgreSQL local.
Cada petición y todos sus scripts leen la misma versión inmutable.

GET /v1/catalog/summary y POST /v1/catalog/refresh operan sobre el catálogo
configurado por entorno, no sobre el último snapshot de una conversación.

## Inferencia

POST /v1/query:

```json
{
  "prompt": "Revistas de inteligencia artificial para ingeniería de sistemas",
  "model_name": "qwen",
  "previous_prompt": "",
  "previous_topic": "",
  "catalog_digest": "<sha256 de 64 caracteres>",
  "return_analysis": true
}
```

Es síncrona y puede incluir arranque en frío. model_name debe coincidir con
esta réplica: no cambia pesos. previous_prompt permite continuar una consulta;
previous_topic conserva su tema validado al modificar únicamente filtros.

Con return_analysis retorna respuesta, analisis, modelo y catalog_digest.
El Backend valida IDs y solo publica respuesta. Sin esa opción devuelve el
contrato bibliográfico directamente: estado, mensaje, programas_seleccionados,
busquedas, filtros_no_aplicados. Estado puede ser ok, fuera_de_tema,
informacion_insuficiente o error_sistema. Un ok requiere programas/búsquedas
no vacíos y mensaje=null.

Cada programa: id, nombre, puntuacion, razon. Cada búsqueda: plataforma_id,
plataforma, cadena, justificacion. Cada filtro no aplicado: plataforma_id,
plataforma, filtro.

## Drenaje y diagnóstico

- GET /v1/control/status: accepting_requests e inflight.
- POST /v1/control/drain: cierra admisión sin interrumpir consultas.
- POST /v1/control/resume: reabre admisión.
- GET /v1/models: identidad del modelo.
- GET /health y /ping: liveness.
- GET /ready: configuración vLLM, no prueba completa de inferencia.
- GET /health/details: diagnóstico del proceso.

El contador incluye consultas admitidas esperando el semáforo. El Backend
confirma inflight=0 antes de cambiar. Drenaje devuelve 503 y saturación 429.
Un proceso API por réplica y una réplica Modal por modelo: no aumentar workers
o max_containers sin coordinación distribuida de estos contadores.
