# Agente de Biblioteca

Servicio FastAPI preparado exclusivamente para desplegarse como imagen en
RunPod. La imagen no contiene vLLM, pesos, CUDA ni mecanismos de ejecución de
modelos locales: enruta cada consulta a uno de tres endpoints vLLM remotos.

## Documentación

- [API](./docs/api.md): endpoints, autenticación y ejemplos.
- [RunPod](./docs/runpod.md): construcción y configuración del despliegue.
- [Arquitectura](./docs/architecture.md): capas y decisiones técnicas.
- [SKILL](./SKILL.md): comportamiento del agente y contratos de herramientas.

## Estructura

- `config/models.json`: registro versionado de Qwen, GLM y Llama.
- `src/biblioteca_agent/`: API, orquestación, RAG y adaptadores.
- `scripts/`: herramientas deterministas del catálogo y YAKE.
- `resources/`: prompt, datos RAG aprobados y snapshot de demostración.
- `Dockerfile`: única imagen desplegable del agente.

No existe `docker-compose.yml` ni servidor de inferencia local. Las URL y API
keys de RunPod se inyectan como secretos; nunca se guardan en el registro.

## Validación en CI

Las pruebas no requieren GPU ni vLLM:

```bash
python -m unittest discover -s tests -v
```
