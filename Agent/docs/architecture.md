# Arquitectura y decisiones

| Capa | Responsabilidad |
| --- | --- |
| Django | API pública, permisos, chats anónimos, rankings y selección global. |
| PostgreSQL | Turnos, temas y estado transaccional; ninguna relación con cuentas. |
| Celery agent | Inferencia asíncrona fuera del ciclo HTTP. |
| Celery agent-control | Drenaje y cambio, separado de la inferencia. |
| FastAPI | Autenticación privada, validación, admisión y snapshots inmutables. |
| Runtime | RAG, clasificación vLLM, filtros, relaciones y respuesta. |
| Scripts | Allowlist, JSON, timeout, sin shell ni credenciales de PostgreSQL. |
| vLLM | Un checkpoint por despliegue, continuous batching. |

Los perfiles deploy/models/*.env configuran Qwen, GLM y Llama, sin duplicar
src ni usar models.json. En Modal son despliegues privados independientes.
El Backend enruta al activo. Cambiar termina los trabajos admitidos, drena
el origen, valida/reactiva el destino y confirma la nueva ruta. No sustituye
pesos en una GPU: el origen deja de recibir tráfico y escala a cero tras
inactividad, no se promete liberación instantánea de VRAM.

Cada snapshot se identifica por SHA-256. El contexto de petición propaga esa
versión a los scripts, evitando mezclar catálogos concurrentes. El agente
nunca accede directamente a PostgreSQL. El RAG se reconstruye desde ejemplos
aprobados, no aprende automáticamente de conversaciones. YAKE se conserva.

El modelo clasifica intención; el servidor calcula relaciones, cobertura,
sintaxis y justificación con datos reales. Una continuación hereda contexto
solo cuando el clasificador identifica seguimiento; filtros explícitos nuevos
reemplazan al filtro anterior de su misma clase.
Una pregunta autónoma reinicia esos filtros aunque el modelo la marque como
seguimiento. Los ajustes exclusivamente de filtros conservan el tema validado
anterior; se limita a tres áreas implícitas y tres ambiguas por clasificación
para impedir que un modelo copie todo el catálogo como evidencia relevante.

UUID de mensaje asegura idempotencia. Redelivery no repite una inferencia
iniciada. Un reconciliador recupera publicaciones/cambios pendientes. Ante fallo
del destino se conserva el origen y se bloquea admisión hasta recuperación o
cancelación. El diseño exige un controlador de cambios y un proceso API por
modelo. La cola reside en Backend, no se duplica en el agente.

Los chats no guardan identidad, cookies ni IP. Redactar patrones personales
no garantiza anonimización semántica perfecta del texto libre: la interfaz
debe pedir no introducir datos personales. Ver la guía pública del Backend.
