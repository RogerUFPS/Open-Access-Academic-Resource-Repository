# Despliegue en RunPod

## Topología

Se usa una sola imagen del agente y tres despliegues vLLM independientes:

```text
cliente -> Agent API -> endpoint Qwen vLLM
                    -> endpoint GLM vLLM
                    -> endpoint Llama vLLM
                    -> scripts + RAG + snapshot de catálogo
```

No son tres copias de `src/`. El parámetro `model_name` hace que el registro
`config/models.json` elija endpoint, credencial, nombre servido y opciones de
solicitud. Separar los modelos permite asignar GPU, escalado y workers distintos
sin reconstruir el agente.

## 1. Crear los endpoints de inferencia

Cree tres endpoints vLLM Serverless o Load Balancer en RunPod. Los valores de
`checkpoint`, `served_model` y las opciones de tool calling están declarados en
`config/models.json`; deben coincidir con la configuración efectiva de vLLM.

| Alias API | Checkpoint declarado | Nombre servido |
| --- | --- | --- |
| `qwen` | `Qwen/Qwen3-8B` | `biblioteca-qwen3-8b` |
| `glm` | `THUDM/glm-4-9b-chat-hf` | `biblioteca-glm4-9b` |
| `llama` | `meta-llama/Meta-Llama-3.1-8B-Instruct` | `biblioteca-llama3.1-8b` |

Todos deben exponer Chat Completions OpenAI-compatible y tool calling automático.
En Llama 3.1 configure `llama3_json` y su plantilla JSON. En Qwen use el parser
declarado en el registro. Valide GLM con la versión concreta de vLLM elegida:
el checkpoint soporta function calling, pero su parser no está documentado por
vLLM con la misma estabilidad que GLM 4.5/4.7.

Si el modelo es gated, agregue `HF_TOKEN` únicamente al endpoint de inferencia
correspondiente.

## 2. Construir la imagen del agente

Publique el contenido de `Agent/` como raíz de su repositorio dedicado. En
**New Endpoint → Import Git Repository**, seleccione la rama y use `Dockerfile`
como **Dockerfile Path**. RunPod construirá y almacenará la imagen. Elija
**Load Balancer**, no **Queue**, porque este contenedor expone una API FastAPI y
no un handler de jobs.

Si decide conservar todo Biblioteca como monorepo, el Dockerfile actual no debe
usarse con contexto raíz: cree el repositorio dedicado o adapte sus rutas `COPY`.
Si usa un registro externo, el equivalente de CI desde el monorepo es:

```bash
docker build -t REGISTRY/biblioteca-agent:VERSION Agent
docker push REGISTRY/biblioteca-agent:VERSION
```

La imagen expone el puerto `8000`, ejecuta como usuario sin privilegios y usa
`/ping` como health check. Configure un worker CPU para esta API; las GPU solo
pertenecen a los tres endpoints vLLM.

## 3. Secretos y variables del endpoint del agente

```text
PORT=8000
PORT_HEALTH=8000
HEALTH_CHECK_PATH=/ping
AGENT_API_KEY=...
QWEN_VLLM_BASE_URL=https://api.runpod.ai/v2/QWEN_ID/openai/v1
QWEN_VLLM_API_KEY=...
GLM_VLLM_BASE_URL=https://api.runpod.ai/v2/GLM_ID/openai/v1
GLM_VLLM_API_KEY=...
LLAMA_VLLM_BASE_URL=https://api.runpod.ai/v2/LLAMA_ID/openai/v1
LLAMA_VLLM_API_KEY=...
```

Una misma RunPod API key puede asignarse a las tres variables si tiene acceso a
los tres endpoints. Se mantienen variables separadas para permitir rotación y
proveedores diferentes. Las URL deben terminar en `/v1`.

`PORT_HEALTH` debe coincidir con `PORT`: RunPod usa `80` por defecto para salud
y, si se omite, el worker que escucha en `8000` nunca queda disponible.

Mientras Biblioteca no sea accesible desde RunPod:

```text
AGENT_CATALOG_SNAPSHOT=/app/resources/catalog_snapshot.example.json
AGENT_BACKEND_SNAPSHOT_URL=
```

Cuando se autorice la integración, use una URL HTTPS de solo lectura en
`AGENT_BACKEND_SNAPSHOT_URL`. El agente nunca debe conectarse a PostgreSQL.

## 4. Cambiar modelos

- Cambiar solo URL o credencial: actualice el secret de RunPod.
- Cambiar checkpoint, alias, nombre servido o capacidad: edite
  `config/models.json`, cree una versión de imagen y despliegue esa versión.
- Cambiar el modelo predeterminado: edite `default_model` en ese archivo.

Esto deja toda la configuración no secreta en el directorio y evita imágenes
distintas por modelo.

## 5. Probar

```bash
AGENT_API_URL='https://ENDPOINT_AGENT' \
AGENT_API_KEY='...' \
  ./query_agent.sh --model qwen \
  'Artículos sobre inteligencia artificial aplicada a educación'
```

Repita con `--model glm` y `--model llama`. Consulte primero `GET /ready` para
detectar variables faltantes; ese endpoint no despierta los tres modelos.

## Persistencia

El índice RAG aprobado se reconstruye en cada cold start. No existe una API de
ingesta mutable porque el disco de un worker Serverless puede ser efímero y no
se comparte entre réplicas.

## Referencias oficiales

- [Configuración de endpoints RunPod](https://docs.runpod.io/serverless/endpoints/endpoint-configurations)
- [Despliegue desde GitHub](https://docs.runpod.io/serverless/workers/github-integration)
- [Load Balancer con FastAPI](https://docs.runpod.io/serverless/load-balancing/overview)
- [Worker vLLM de RunPod](https://github.com/runpod-workers/worker-vllm)
- [Tool calling de vLLM](https://docs.vllm.ai/en/stable/features/tool_calling/)
