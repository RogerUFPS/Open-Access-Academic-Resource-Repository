# Agente de Biblioteca

Servicio FastAPI con clasificación vLLM, herramientas Python, YAKE y RAG SQLite
FTS5. El mismo código corre en Docker local y Modal. La entrada pública es el
Backend: conserva chats anónimos, permisos, estadísticas y modelo activo, y
envía un snapshot inmutable del catálogo real.

- [Despliegue Modal y local](docs/despliegue_modal_y_local.md).
- [API privada](docs/api.md).
- [Arquitectura](docs/architecture.md).
- [SKILL](SKILL.md).
- Guía pública: `../guia_implementacion_chat.md` en el repo de Biblioteca.

Pruebas automatizadas sin GPU:

```bash
docker compose --profile test run --build --rm --no-deps tests
```

Se mantienen las pruebas de regresión; se retiraron clientes shell y reportes
manuales antiguos. No se eliminan pesos ni secretos.
