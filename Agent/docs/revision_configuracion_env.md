# Revisión de configuración por servicio

## Cambios realizados

Se eliminaron todos los bloques `environment` de ambos Compose. No se editaron
archivos privados ni se iniciaron GPU o despliegues Modal. Los ejemplos son
plantillas para revisión y copia manual: no se utilizan como configuración de
producción.

- El Compose raíz consume los archivos de cada servicio mediante `env_file`.
- La API local y vLLM leen primero el perfil de modelo y después `Agent/.env`;
  por tanto, una variable explícita en el archivo privado tiene prioridad.
- Las pruebas del agente no cargan el archivo privado de producción: consumen
  el perfil y opcionalmente `tests/.env`, que el mantenedor debe preparar con
  [su plantilla](../tests/.env.example). Ese archivo contiene el catálogo fixture.
- Las pruebas del backend leen la misma configuración de conexión del backend,
  sin sustituirla con credenciales del archivo de PostgreSQL.
- Si existe `Backend/.agent.env`, conserva prioridad sobre `Backend/.env`.
  En esta revisión no existía ese archivo adicional.
- El perfil `local-agent` sigue siendo obligatorio para iniciar la GPU local.

`--env-file Agent/.env` sigue siendo necesario desde la raíz para interpolar
el perfil elegido, puerto y alias de red. No crea un archivo en la raíz ni
sustituye los `env_file` de los servicios.

## Resultado de la revisión de archivos privados

Se compararon valores sin incluirlos en este informe. Coinciden las
credenciales Backend/PostgreSQL, Backend/RabbitMQ y Backend/RustFS.
La conexión del backend apunta al PostgreSQL interno por el puerto correcto
y tiene SSL desactivado para esa conexión local. El frontend apunta al
backend interno correcto. No se validó conectividad externa ni autenticación
real contra Modal en esta revisión.

### Agente: pendientes para ejecución local

Añadir manualmente a `Agent/.env`:

```dotenv
AGENT_INSTANCE=qwen
AGENT_VLLM_BASE_URL=http://vllm:8000/v1
AGENT_VLLM_API_KEY=<una-clave-privada-compartida-entre-api-y-vllm>
HF_HOME=/root/.cache/huggingface
RAG_DB_PATH=/tmp/biblioteca/rag.sqlite3
VLLM_MAX_MODEL_LEN=8192
VLLM_GPU_MEMORY_UTILIZATION=0.90
VLLM_MAX_NUM_SEQS=8
```

La URL de inferencia es necesaria. La clave protege el motor privado. Las otras
variables hacen explícitos el alias, las rutas y los límites que antes imponía
Compose; algunas tienen valores predeterminados en el código o dependencias.
`AGENT_INSTANCE` debe coincidir con el perfil seleccionado.

`HF_TOKEN` no existe: añadirlo solo cuando el checkpoint requiera autorización,
como Llama. Esto no lo registra automáticamente como Secret de Modal.

`AUTO_INDEX_RAG` ya está definido. El puerto interno configurado es compatible
con las comprobaciones de salud actuales.

La URL de catálogo existente apunta fuera del Docker local. Para leer la base
local en ejecución aislada, cambiarla manualmente a:

```dotenv
AGENT_BACKEND_SNAPSHOT_URL=http://backend:8000/api/agent/v1/snapshot/
```

El cliente espera la URL completa del snapshot, no solo el dominio del backend.
La URL externa actual solo especifica un dominio: revisar y completar su ruta.
La dirección interna requiere la red compartida del Compose raíz. No es válida
desde Modal; allí se necesita un backend públicamente accesible, o el catálogo
enviado por el backend mediante el protocolo del agente.

### Backend

- Falta `DATABASE_POOL`: dejarlo explícitamente en `0` es compatible con todos
  los procesos que comparten el archivo. Al retirar Compose, el web deja de
  tener el pool que se activaba por sobrescritura. Activarlo globalmente también
  afecta a Celery e inicialización; no hacerlo sin evaluar ese alcance.
- Falta `DJANGO_TESTING`: `0` conserva PostgreSQL para las pruebas de integración.
- Existe una errata: `LINKE_FAILURE_FRONTEND_URL` debe renombrarse a
  `LINK_FAILURE_FRONTEND_URL`, conservando el destino que corresponda.
- `SCHEDULER_API_TOKEN` y `SCHEDULER_SERVICE_USER_ID` conservan marcadores de
  ejemplo: configurar un secreto real y el usuario de servicio autorizado.
- `AGENT_DEFAULT_MODEL` falta; el código usa Qwen como valor predeterminado.
  Añadirlo si se desea explicitar la selección inicial. No reemplaza la
  selección activa ya persistida en PostgreSQL.
- `AGENT_SERVICE_API_KEY` falta: es necesaria si se conecta al agente local
  protegido por `AGENT_API_KEY`; ambas deben coincidir. Las URLs Qwen/GLM y las
  credenciales de proxy Modal ya están definidas. No se verificaron contra Modal.
- No hay URL Llama configurada: no habilitarla hasta desplegar ese modelo.

### RustFS

El archivo privado solo configura credenciales. Para conservar exactamente los
ajustes que antes imponía Compose, añadir:

```dotenv
RUSTFS_ADDRESS=:9000
RUSTFS_CONSOLE_ADDRESS=:9001
RUSTFS_CONSOLE_ENABLE=true
RUSTFS_OBS_LOGGER_LEVEL=error
RUSTFS_OBS_LOG_DIRECTORY=/var/log/rustfs/
```

La consola y las rutas/puertos deben coincidir con los publicados y montados.
No se garantiza ese comportamiento mientras se dependa de los valores propios
de la imagen, especialmente porque está etiquetada `latest`.

### Frontend

Faltan `CSP_IMG_SRC`, `NEXT_PUBLIC_SESSION_COOKIE_NAME` y
`NEXT_PUBLIC_CSRF_COOKIE_NAME`, documentadas en su plantilla existente.
Para imágenes RustFS por HTTP local, configurar `CSP_IMG_SRC=http://localhost:9000`.
Los nombres de cookies deben coincidir con los del backend.

No se modificó ningún archivo de Frontend. Atención: sus variables `NEXT_PUBLIC_*`
se incorporan durante el build, no solo al arrancar. Los argumentos de build
del Compose y del Dockerfile siguen existiendo; este cambio elimina únicamente
los bloques `environment` de Compose. Una configuración exclusivamente desde
su archivo privado también durante el build necesita revisar ese flujo aparte.

### RabbitMQ y PostgreSQL

Los archivos existen, sus claves principales están definidas y sus credenciales
coinciden con las utilizadas por el backend. No faltan las variables básicas
de arranque comprobadas.

## Comprobación y puesta en marcha

Verificación realizada: ambos Compose válidos (incluidos perfiles local y
pruebas), sin errores del editor ni de `git diff --check`. Las 49 pruebas del
agente pasaron en Docker sin red ni GPU, cargando el perfil Qwen y la plantilla
de configuración exclusiva de pruebas. La primera ejecución omitió el perfil
y falló una prueba de alias; al repetir con los mismos archivos que requiere
Compose, pasaron las 49. No se ejecutaron pruebas de inferencia GPU ni Modal.

Primero resolver los pendientes manualmente; luego, desde la raíz:

```bash
docker compose config --quiet
docker compose --env-file Agent/.env --profile local-agent config --quiet
```

Editar un archivo privado no actualiza contenedores existentes: recrear los
servicios afectados cuando se quiera aplicar la configuración. No se recrearon
servicios durante esta revisión para no aplicar una configuración incompleta.

No publicar la salida completa de `docker compose config`: contiene secretos
resueltos. Un error de una herramienta de diagnóstico incluyó esa salida durante
esta revisión; conviene rotar las credenciales reales de los archivos afectados
(Modal, Django, PostgreSQL, RabbitMQ, RustFS y API del agente). No se copiaron
esas credenciales a este documento ni a archivos versionados.
