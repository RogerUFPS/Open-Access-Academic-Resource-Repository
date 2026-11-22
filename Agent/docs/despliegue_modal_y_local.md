# Despliegue local y adaptador temporal de Modal

Los Compose no declaran bloques `environment`: cada servicio consume su
configuración privada mediante `env_file`. Antes de arrancar, revisar los
[pendientes de configuración manual](revision_configuracion_env.md).
Los ejemplos no se copian ni se aplican automáticamente.

## Qué se entrega para funcionar localmente

Dockerfile, docker-compose.yml, requirements.txt, src, scripts, SKILL.md,
resources, deploy/start_vllm.py, deploy/model_config.py y deploy/models.
La imagen y dependencias de la API local no incluyen el SDK de Modal.
Las pruebas automatizadas y sus fixtures se conservan en tests, fuera de la imagen.

Toda la dependencia específica de Modal está en **deploy/modal/**:
app.py (despliegue), tasks.py (descarga CPU opcional), configure_backend.py
(provisionamiento privado), profile.py (lector de perfiles) y requirements.txt
(SDK de despliegue). Para una entrega exclusivamente local se puede eliminar
esa carpeta sin cambiar el runtime, los perfiles o los Compose locales.
El servicio Docker modal-cli fue retirado: el operador ya tiene Modal instalado.
No se restauran Dockerfiles, referencias ni guías previamente eliminados.

## Sistema completo desde la raíz

1. Copiar Agent/.env.example a Agent/.env y asignar AGENT_API_KEY robusta.
2. En Backend/.agent.env configurar:

```dotenv
AGENT_QWEN_URL=http://biblioteca-agent-qwen:8000
AGENT_GLM_URL=
AGENT_LLAMA_URL=
AGENT_SERVICE_API_KEY=<la misma AGENT_API_KEY del agente>
AGENT_MODAL_KEY=
AGENT_MODAL_SECRET=
```

No seleccionar un modelo cuyo endpoint no esté desplegado.
AGENT_DEFAULT_MODEL solo inicializa el estado; la selección activa se conserva
en PostgreSQL y se cambia con el endpoint administrativo.

3. Ejecución habitual, sin inferencia local:

```bash
docker compose up -d
```

4. Solo cuando se quiera levantar también el agente GPU:

```bash
docker compose --env-file Agent/.env --profile local-agent up --build -d
```

El Compose raíz incorpora las definiciones del agente mediante extends y
declara sus redes. No hace falta docker-compose.backend.yml: se retiró.
agent-api se conecta a la red services con alias biblioteca-agent-qwen y a
agent-inference; vllm solo se conecta a agent-inference y no publica puertos.
El peso del modelo se almacena en el volumen huggingface-cache, no en Git.
Un up normal no inicia esos servicios; tampoco apaga los que ya estén activos.
Para apagarlos sin borrar pesos: docker compose --profile local-agent stop agent-api vllm.

El equipo necesita GPU NVIDIA, drivers y NVIDIA Container Toolkit compatibles.
El perfil carga un modelo por instancia, no los tres. Los otros modelos
necesitan endpoints/GPU provisionados: los perfiles no aportan VRAM.
Para ejecutar solamente el agente, usar su propio Compose dentro de Agent.
El Backend local se conecta desde el orquestador raíz, no desde un overlay externo.

## Pruebas actuales en Modal

No iniciar api/vllm locales ni activar local-agent. Mantener Backend, RabbitMQ,
agent-worker, agent-control y beat, que hacen las llamadas HTTP y coordinación.

Con el SDK de Modal instalado, desde Agent:

```bash
MODEL_ENV_FILE=deploy/models/qwen.env modal run deploy/modal/tasks.py::download_model
MODEL_ENV_FILE=deploy/models/qwen.env modal deploy deploy/modal/app.py
```

Los perfiles se leen sin usar source, para conservar correctamente su JSON.
Cambiar MODEL_ENV_FILE a deploy/models/glm.env o deploy/models/llama.env.
MODAL_GPU y MODAL_HF_SECRET son variables exclusivas del adaptador; ver su
archivo .env.example (exportarlas en el entorno si se necesitan).
La descarga previa usa CPU y es opcional. app.py inicia vLLM y después FastAPI
al nacer un worker. Se configura L4, cuatro CPU, 16 GiB, min_containers=0,
max_containers=1 y ventana inactiva de 30 s. Arrancar en frío tiene latencia.
Llama requiere aceptar la licencia y un Secret Modal con HF_TOKEN autorizado.

En Backend/.agent.env registrar las URLs HTTPS privadas, AGENT_MODAL_KEY y
AGENT_MODAL_SECRET. configure_backend.py sigue disponible, pero solo se ejecuta
explícitamente; su salida predeterminada presupone /backend/.agent.env.
Desde el sistema usar --output con la ruta real, por ejemplo desde Agent:

```bash
python deploy/modal/configure_backend.py --output ../Backend/.agent.env --qwen-url https://SU-ENDPOINT.modal.direct
```

Nunca imprimir ni entregar estas claves al navegador. El script crea/reutiliza
un Proxy Token y guarda el archivo privado. No es necesario para cada consulta.

## Limitación de credenciales: explicación

AGENT_MODAL_KEY/SECRET eran un único par global que se añadía a todas las URLs:
si quedaban configurados al cambiar a una URL local, el Backend también enviaba
esas credenciales al agente local. Eso no significa que la inferencia dependiera
de Modal; era una selección demasiado amplia de headers.

Se corrigió: esos headers se envían únicamente a hosts terminados en
.modal.direct. X-API-Key es la autenticación independiente del servicio local.
Ahora pueden coexistir endpoints locales y Modal sin reenviar Proxy Tokens al
destino local. Sigue existiendo un solo par para todos los endpoints Modal:
varios Workspaces con credenciales distintas requieren configuración por destino.
Dominios personalizados de Modal no se detectan automáticamente; usar la URL
.modal.direct con este cliente.

Recrear Backend y workers tras cambiar variables; no basta editar el archivo:

```bash
docker compose up -d --no-deps --force-recreate backend agent-worker agent-control beat
```

Los tokens deben permanecer ignorados por Git. Modal no interpreta el Compose
raíz: ejecuta el adaptador Python. La ejecución local no importa ese adaptador.
