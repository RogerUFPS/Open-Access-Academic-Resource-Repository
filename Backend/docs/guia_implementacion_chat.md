# Integración del chat para Frontend

## Respuestas informativas de catálogo

Además de los estados existentes, `response.estado` puede ser
`informacion_catalogo`: una respuesta satisfactoria a una pregunta de cobertura
o cantidades, no una recomendación bibliográfica. Mostrar `mensaje` como
respuesta del agente. `busquedas`, `programas_seleccionados` y
`filtros_no_aplicados` pueden estar vacíos; no generar botones de búsqueda si no
hay cadenas. No se marca el chat como no resuelto solo por este estado.

Ejemplo: preguntar cuántas revistas tiene una plataforma para un programa
devuelve su cantidad real, incluido cero. No interpretar cero como error de red.
Los demás endpoints, autenticación y estados conservan su funcionamiento.

Una recomendación `ok` puede tener cobertura temática parcial. Mostrar
`programas_seleccionados[].razon` y `busquedas[].justificacion` completas: indican
los aspectos respaldados y los que quedan sin cubrir. No convertir un conteo de
revistas en una afirmación de que existen artículos concretos o evidencia de
eficacia. No hay nuevos endpoints ni campos públicos obligatorios para este caso.
`puntuacion` es un criterio de ordenación, no un porcentaje de certeza del modelo.

Los errores recuperables de entrada (por ejemplo, un periodo invertido) usan
`informacion_insuficiente` y explican qué corregir. Los seguimientos aplican
cambios sobre el tema y filtros vigentes; no reenviar todo el historial desde
Frontend. El Backend proporciona el contexto canónico del turno anterior.

## Chat público anónimo

1. `POST /api/agent/chat/conversations/`, JSON `{}` → 201:
   id, created_at, updated_at, has_unclear, turn_count, **access_token**.
   El token se entrega una sola vez; el servidor solo guarda su hash.
2. Guardar id/token de esa conversación, por ejemplo en sessionStorage.
   No compartirlo, enviarlo en URLs ni incluirlo en logs. Es la llave para leer
   y escribir ese chat, no un identificador de persona.
3. `POST /api/agent/chat/conversations/{id}/messages/` con
   `X-Chat-Token: <access_token>` y JSON:

```json
{
  "prompt": "Revistas sobre inteligencia artificial para ingeniería de sistemas",
  "client_message_id": "a5f13eaa-e502-42b1-9cbb-64793894d947"
}
```

4. Retorna 202 y un turno: id, client_message_id, sequence, prompt, status,
   response, unclear, created_at, finished_at. Mientras status sea queued o
   running, consultar `GET .../messages/{turn_id}/` con el mismo token cada
   2s, con backoff hasta 10s. Respetar Retry-After cuando se incluya.
5. Al terminar, status es completed o failed y response contiene el resultado.
   El arranque en frío puede tardar varios minutos; no reenviar la pregunta
   con otro UUID por un timeout del navegador. Puede retomarse el polling.

El UUID debe ser v4 aleatorio y se conserva en reintentos del **mismo** mensaje.
Un reintento devuelve el mismo turno (202 pendiente, 200 terminado), sin cobrar
otra inferencia. No admite dos preguntas pendientes en un mismo chat.

Historial: `GET /api/agent/chat/conversations/{id}/messages/?page=1&page_size=20`.
Respuesta paginada: current_page, total_pages, page_size, total_items, next,
previous, results. Leer todas las páginas si se necesita el historial completo.
Un token erróneo devuelve 404, igual que una conversación inexistente.

### Ejemplo JavaScript

```javascript
const base = '/api/agent/chat/conversations/';
const created = await fetch(base, {
  method: 'POST', credentials: 'omit',
  headers: {'Content-Type': 'application/json'}, body: '{}'
});
if (!created.ok) throw new Error('No fue posible crear el chat');
const chat = await created.json();
const headers = {'Content-Type': 'application/json', 'X-Chat-Token': chat.access_token};
const clientMessageId = crypto.randomUUID(); // reutilizar si se reintenta
const submitted = await fetch(`${base}${chat.id}/messages/`, {
  method: 'POST', credentials: 'omit', headers,
  body: JSON.stringify({prompt: 'Revistas para ingeniería de sistemas',
                        client_message_id: clientMessageId})
});
if (!submitted.ok) throw new Error(`Solicitud rechazada: ${submitted.status}`);
const turn = await submitted.json();
// Consultar `${base}${chat.id}/messages/${turn.id}/` hasta completed/failed.
```

### Mostrar la respuesta

response contiene estado, mensaje, programas_seleccionados, busquedas y
filtros_no_aplicados. Los estados son ok, informacion_insuficiente,
fuera_de_tema, error_sistema. Un ok tiene mensaje=null: no es un error.
Cada búsqueda incluye plataforma_id, plataforma, cadena y justificacion.
Mostrar la explicación junto a la cadena, y advertir filtros no aplicados.
Renderizar como texto escapado, nunca HTML proveniente de la conversación.
El mensaje siguiente puede ser una continuación, por ejemplo «Y en inglés».

Errores HTTP relevantes:

| Código | Acción Frontend |
| --- | --- |
| 400 | Corregir prompt (3–4000 caracteres), UUID o campos no permitidos. |
| 404 | Token/chat/turno inexistente; no revelar ni reintentar credenciales. |
| 409 conversation_busy | Esperar la respuesta anterior. |
| 429 agent_busy | Esperar Retry-After; conservar UUID. |
| 503 model_switch_pending | Mostrar cambio de modelo y reintentar después. |
| 503 agent_unavailable | Modelo no configurado; aviso de indisponibilidad. |

Un fallo durante inferencia queda persistido como turno failed con
response.estado=error_sistema. No es necesario duplicar el mensaje.

## Administración

Estas rutas sí usan la autenticación de administrador existente, sus reglas de
cuenta/MFA y CSRF para POST. Usar el flujo actual de sesión/CSRF del proyecto,
`credentials: "include"` y X-CSRFToken según corresponda; no X-Chat-Token.
Para inicializar CSRF, `GET /api/accounts/auth/csrf/` establece la cookie
configurada; no devuelve el token dentro del JSON. Reutilizar el lector de esa
cookie del cliente administrativo existente al preparar X-CSRFToken.

| Endpoint | Permiso específico |
| --- | --- |
| GET /api/agent/models/ | agent.models.view |
| POST /api/agent/models/switch/ | agent.models.update |
| POST /api/agent/models/cancel/ | agent.models.update |
| GET /api/agent/conversations/ | agent.conversations.view |
| GET /api/agent/conversations/{id}/ | agent.conversations.view |
| GET /api/agent/analytics/topics/ | agent.analytics.view |
| GET /api/agent/analytics/queries/ | agent.analytics.view |

El catálogo de permisos existente incluye estas claves; el superadministrador
puede asignarlas por el mecanismo actual. Un usuario normal no puede leer
historiales ajenos, cambiar modelo ni ver estadísticas.

### Modelo activo y cambio seguro

GET models devuelve active_model, pending_model, phase, inflight, generation,
last_error y available_models con name/configured para qwen, glm, llama.
configured indica configuración disponible, **no** una prueba remota de salud.

POST switch con `{"model":"glm"}` devuelve 202 si queda pendiente, 200 si ya
estaba activo, 409 ante destino no configurado o cambio incompatible pendiente.
Consultar GET models cada 3–5s. No mostrar el destino como activo hasta que
active_model coincida, pending_model sea null y phase sea ready.

El controlador cierra nuevas admisiones, termina todos los turnos aceptados
(incluidos los en cola), confirma el drenaje remoto y valida/reactiva destino.
Solo entonces cambia la ruta. Phase: ready, draining, switching o error.
En error conserva el origen y reintenta periódicamente; mostrar last_error.
POST cancel sin cuerpo cancela/reactiva origen cuando sea seguro (409 si ya
está ejecutando el cambio). Los turnos existentes no se interrumpen.
El proveedor apaga por inactividad el origen: no es descarga instantánea de
pesos ni se mantienen tres modelos en una GPU pequeña.

### Conversaciones con alguna respuesta poco clara

GET conversations/?unclear=true devuelve chats con has_unclear=true. Basta
una respuesta no ok, un error o filtros no aplicados en cualquier turno; el
indicador permanece aunque después haya respuestas correctas. No se limita
a la última pregunta ni a chats cortos. unclear=false permite el conjunto
complementario; sin filtro lista todos. Es una clasificación conservadora,
no una evaluación humana de calidad.

GET conversations/{id}/ pagina todos sus turnos, incluyendo model_name para
auditoría técnica; no hay nombre, cuenta, dirección IP ni identidad de autor.

### Ranking y consultas frecuentes

GET analytics/topics/?kind=program&limit=20&since=2026-01-01&until=2026-12-31.
kind puede ser program o area; fechas opcionales inclusivas, limit 1–100.
Devuelve results con catalog_id, name, queries, conversations y tier. Tier es
ranking denso: iguales frecuencias comparten posición (1,1,2...). Un tema se
cuenta una vez por turno; no se cuentan todas las recomendaciones como interés
explícito. Las áreas relacionadas pueden derivarse del programa consultado.
conversations cuenta chats, **no personas**. Un chat puede consultar varios temas.

GET analytics/queries/ devuelve hasta 100 textos normalizados agrupados con
prompt_key, prompt, queries y conversations. Normaliza mayúsculas/espacios,
no agrupa semánticamente paráfrasis. No hay analítica de usuarios únicos.
