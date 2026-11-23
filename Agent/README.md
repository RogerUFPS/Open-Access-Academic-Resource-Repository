# Agente de Biblioteca

Servicio local FastAPI + vLLM, herramientas Python, YAKE y RAG SQLite FTS5.
El Backend es la entrada pública y envía el catálogo real por snapshots privados.

## Ejecución

- Sistema completo: el [Compose raíz](../docker-compose.yml) integra el agente
  exclusivamente con el perfil optativo `local-agent`.
- Servicio independiente: [Compose del agente](docker-compose.yml).
- Cloud temporal: todo el adaptador está en [deploy/modal/](deploy/modal/).
  No se requiere Modal para ejecutar localmente.

Desde la raíz, configurar las claves/URLs según la [guía](docs/despliegue_modal_y_local.md):

```bash
docker compose up -d
# Solo cuando se requiera GPU e inferencia local:
docker compose --env-file Agent/.env --profile local-agent up --build -d
```

El primer comando no levanta vLLM ni la API local del agente. Los workers del
Backend sí están activos: también se necesitan cuando el agente está en Modal.

- [Despliegue local y separación de Modal](docs/despliegue_modal_y_local.md).
- [API privada](docs/api.md).
- [Arquitectura](docs/architecture.md).
- [Edición de ejemplos RAG](resources/rag/README.md).

## Recursos de producción

- `resources/prompts/intent_classifier.md`: instrucciones del clasificador.
- `resources/keywords/stopwords.json`: exclusiones de YAKE.
- `resources/rag/approved_examples.json`: ejemplos revisados en JSON legible.

No hay catálogo de demostración en producción ni fallback silencioso. El
catálogo artificial se conserva únicamente en `tests/fixtures/catalog.json`.

Pruebas CPU desde este directorio:

```bash
docker compose --profile test run --build --rm --no-deps tests
```
