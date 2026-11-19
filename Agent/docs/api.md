# API del agente

Defina una URL del endpoint desplegado para los ejemplos:

```bash
export AGENT_API_URL='https://ENDPOINT_AGENT'
export AGENT_API_KEY='una-clave-larga'
```

Todas las rutas `/v1/*` requieren `X-API-Key` cuando `AGENT_API_KEY` está
configurada. `/ping`, `/health` y `/ready` son rutas operativas.

## Salud

```bash
curl -sS "$AGENT_API_URL/ping"
curl -sS "$AGENT_API_URL/health"
curl -sS "$AGENT_API_URL/ready"
```

- `GET /ping`: confirma que el proceso HTTP responde.
- `GET /health`: informa concurrencia y cantidad de documentos RAG.
- `GET /ready`: verifica que los tres endpoints tengan URL y secreto. No hace
  una inferencia ni provoca tres cold starts.

## Modelos configurados

```bash
curl -sS "$AGENT_API_URL/v1/models" -H "X-API-Key: $AGENT_API_KEY"
```

Devuelve los modelos del registro, alias, checkpoint informativo, nombre servido
y si sus secretos están configurados. Los nombres aceptados como `model_name`
son `qwen`, `glm`, `llama` y los alias declarados en `config/models.json`.

## Consultar

```bash
curl -sS -X POST "$AGENT_API_URL/v1/query" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{
    "prompt": "Artículos sobre inteligencia artificial aplicada a educación",
    "model_name": "qwen"
  }'
```

`model_name` es opcional y usa `qwen` por defecto. La solicitud es síncrona y
stateless. Cada réplica admite `AGENT_MAX_CONCURRENCY` consultas activas; cuando
se satura responde `429` con `Retry-After` en vez de mantener una cola local.
Una configuración faltante del modelo elegido devuelve `503`.

La respuesta exitosa cumple el contrato de la skill:

```json
{
  "estado": "ok",
  "mensaje": null,
  "programas_seleccionados": [],
  "busquedas": [],
  "filtros_no_aplicados": []
}
```

## Catálogo

- `GET /v1/catalog/summary`: resume el snapshot activo.
- `POST /v1/catalog/refresh`: invalida la caché HTTP del snapshot.

No existen endpoints `load` o `unload`. Cada modelo vive en su propio endpoint
vLLM y RunPod administra sus workers; seleccionar un modelo consiste en enrutar
la solicitud, no intercambiar pesos dentro del contenedor del agente.

## Cliente incluido

```bash
AGENT_API_URL="$AGENT_API_URL" AGENT_API_KEY="$AGENT_API_KEY" \
  ./query_agent.sh --model llama \
  'Investigaciones sobre bases de datos distribuidas'
```

El cliente reintenta respuestas `429` y errores temporales. Use
`AGENT_RETRIES` para cambiar el máximo.

## Variables

| Variable | Uso |
| --- | --- |
| `AGENT_API_KEY` | Autenticación de clientes. |
| `PORT`, `PORT_HEALTH` | Puerto HTTP y de salud; ambos deben valer `8000`. |
| `HEALTH_CHECK_PATH` | Ruta de salud de RunPod; use `/ping`. |
| `AGENT_MODEL_REGISTRY` | Ruta del registro; por defecto `/app/config/models.json`. |
| `QWEN_VLLM_BASE_URL`, `QWEN_VLLM_API_KEY` | Endpoint Qwen. |
| `GLM_VLLM_BASE_URL`, `GLM_VLLM_API_KEY` | Endpoint GLM. |
| `LLAMA_VLLM_BASE_URL`, `LLAMA_VLLM_API_KEY` | Endpoint Llama. |
| `VLLM_MAX_TOKENS` | Máximo por ronda del tool loop. |
| `VLLM_REQUEST_TIMEOUT_SECONDS` | Timeout hacia cada endpoint remoto. |
| `AGENT_BACKEND_SNAPSHOT_URL` | Catálogo HTTPS de solo lectura. |
| `AGENT_CATALOG_SNAPSHOT` | Fixture incluido mientras no se integra el Backend. |
