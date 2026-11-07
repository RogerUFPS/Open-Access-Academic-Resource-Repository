# API de `platforms` - Fase A

> **Vigencia, 2 de noviembre de 2026:** este documento conserva instrucciones
> históricas de Fase A. El workspace actual es el repositorio general, con
> `Backend/`, `Frontend/`, `RabbitMQ/`, `Cron/` y `docker-compose.yml` en la raíz.
> Los endpoints administrativos requieren sesión y permisos de aplicación;
> no se utiliza JWT. Para el monitor automático y los comandos actuales, usar
> la sección «Monitoreo automático de enlaces» al final. La validación de
> OpenAPI indicada históricamente no valida estos cambios nuevos.

Esta guía permite levantar el proyecto y probar la API de `platforms` sin leer el código.
Durante la Fase A no se exige autenticación del cliente: las operaciones utilizan el usuario del sistema con `code=0`.
La autenticación JWT y los permisos pertenecen a la Fase B.

## 1. Requisitos

- Docker Desktop iniciado.
- Git.
- Un archivo `.env` en la raíz del proyecto.

Debes crear un archivo `.env` en la raíz del proyecto y completar los datos de la base de datos. El archivo `.env` real no debe subirse a Git porque contiene credenciales.

## 2. Preparar y levantar el proyecto

Ejecuta los comandos desde la raíz del repositorio:

```powershell
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml run --rm web python manage.py migrate
docker compose -f docker/docker-compose.yml run --rm web python manage.py create_system_user
docker compose -f docker/docker-compose.yml run --rm web python manage.py seed_catalog
docker compose -f docker/docker-compose.yml up
```

La API quedará disponible en:

```text
http://localhost:8000
```

Para trabajar con plataformas deben existir previamente los registros de catálogo que se relacionarán con ellas: instituciones, idiomas, países, tipos de material, programas académicos y sus áreas del conocimiento.

## 3. Swagger y esquema OpenAPI

Abre esta URL en el navegador:

```text
http://localhost:8000/api/docs/
```

Para el esquema OpenAPI sin interfaz:

```text
http://localhost:8000/api/schema/
```

En Swagger, selecciona un endpoint, pulsa **Try it out**, completa el cuerpo JSON y pulsa **Execute**.

La validación actual del esquema quedó en:

```text
Warnings: 0
Errors:   0
```

## 4. Recursos disponibles

| Recurso | Ruta base | Uso / campos principales |
| --- | --- | --- |
| Plataformas | `/api/platforms/` | CRUD administrativo de plataformas |
| Sintaxis válidas | `/api/platforms/valid-sintaxis/` | CRUD de configuraciones de sintaxis de búsqueda |
| Verificaciones de enlace | `/api/platforms/link-check-logs/` | Consulta de solo lectura del historial de verificación |
| Plataformas públicas | `/api/platforms/public/` | Consulta de plataformas en estado `PUBLICADO` |

### 4.1. Campos de escritura de `Platform`

```text
name
public_url
is_harvestable
base_api_url
api_key
url_image
requires_registration
has_access_text
valid_sintaxis
institutions
languages
countries
material_types
```

Los siguientes campos son de solo lectura o son controlados por el backend:

```text
id
status
start_period
finish_period
validated_by
validated_at
knowledge_areas
academic_programs
created_by
created_at
updated_by
updated_at
deleted_by
deleted_at
delete_explanation
```

La respuesta de Platform conserva procedencia manual/derivada por sección.
Los programas y las áreas derivados provienen de Journals elegibles. En el
caso de las áreas, Platform consume todas las áreas efectivas de Journal
(`is_manual=true OR is_derived=true`) y las marca como derivadas en el nivel
Platform; no copia los flags de procedencia de Journal.

### 4.2. `is_harvestable`, `base_api_url` y `api_key`

Son datos de configuración de cosecha y son independientes de la URL pública.
`is_harvestable` tiene valor predeterminado `false`; solo pasa a `true` cuando
el cliente lo solicita explícitamente y proporciona una configuración válida.

| `is_harvestable` | `base_api_url` | `api_key` | Resultado |
| --- | --- | --- | --- |
| `false` | `null` | `null` | Válido: plataforma de referencia no cosechable |
| `true` | URL | `null` | Válido: cosecha sin autenticación |
| `true` | URL | valor | Válido: cosecha con credencial |
| `true` | `null` | cualquiera | **Inválido: HTTP 400** |
| `false` | URL o valor | cualquiera | **Inválido: HTTP 400** |

`api_key` es de solo escritura. El backend la almacena cifrada en `encrypted_api_key`, pero ni `api_key` ni `encrypted_api_key` aparecen en las respuestas.

Para cosechas de OpenAlex que avanzan a páginas posteriores mediante cursor,
OpenAlex requiere una API key. Configúrala en `api_key` al crear o actualizar
la plataforma; el harvester la envía como token Bearer en el encabezado de
autorización, sin incluirla en la URL.

En un `PATCH`:

- si `api_key` no se envía, se conserva la credencial actual;
- `"api_key": null` elimina la credencial existente;
- `"api_key": ""` se trata como ausencia de credencial.
- cambiar `is_harvestable` de `true` a `false` limpia automáticamente `base_api_url` y la credencial cifrada.

La migración inicial conserva la configuración histórica: toda plataforma existente con `base_api_url` no nula ni vacía queda con `is_harvestable=true`; las demás quedan en `false`. La migración no modifica la URL técnica ni la credencial almacenada.

### 4.3. URL pública de la plataforma

La implementación actual **no almacena la URL pública en `Platform`**. `public_url` es un campo virtual aceptado en `POST` y `PATCH`; se registra y conserva en `LinkCheckLog.url`, y se devuelve en las respuestas administrativas y públicas.

```text
Platform
    ↓
LinkCheckLog.url   ← URL pública (`journal_platform IS NULL`)

Platform.base_api_url ← API de cosecha
```

La URL pública puede registrarse mediante el campo virtual `public_url` del CRUD normal o verificarse mediante:

```text
POST /api/platforms/{id}/check-link/
```

Una plataforma necesita al menos una URL pública registrada en `LinkCheckLog` antes de poder publicarse.

Si existe historial, `public_url` se obtiene del último registro general no
eliminado. Los logs ligados a una revista mediante `journal_platform` no se
consideran para este campo. `public_url` nunca se toma de `base_api_url`: esta
última continúa siendo exclusivamente la URL técnica de harvesting.

En `PATCH`, omitir `public_url` conserva el historial; enviar la misma URL no duplica logs y enviar una URL distinta crea un nuevo registro. Toda URL recibida pasa por la validación SSRF del backend.

### 4.4. Campos de `ValidSintaxis`

Campos de escritura:

```text
name
booleans
parenthesis
fields
```

`fields_template` es de solo lectura y expone la plantilla canónica:

```json
{
  "title": "",
  "author": "",
  "subject": "",
  "issn": "",
  "language": "",
  "year": ""
}
```

`fields` solo acepta esas claves y valores de tipo string.

## 5. Operaciones generales

### 5.1. Plataformas administrativas

| Método | Ruta | Uso | Respuesta habitual |
| --- | --- | --- | --- |
| GET | `/api/platforms/` | Listar plataformas activas | 200 |
| POST | `/api/platforms/` | Crear plataforma | 201 |
| GET | `/api/platforms/{id}/` | Consultar plataforma | 200 |
| PUT | `/api/platforms/{id}/` | Reemplazar información editable | 200 |
| PATCH | `/api/platforms/{id}/` | Actualizar parcialmente | 200 |
| DELETE | `/api/platforms/{id}/` | Eliminación física o lógica según relaciones | 204/200 |
| GET | `/api/platforms/archived/` | Listar plataformas eliminadas lógicamente | 200 |
| POST | `/api/platforms/{id}/restore/` | Restaurar plataforma eliminada | 200 |
| POST | `/api/platforms/{id}/publish/` | `BORRADOR → PUBLICADO` | 200 |
| POST | `/api/platforms/{id}/mark-obsolete/` | `PUBLICADO → OBSOLETO` | 200 |
| POST | `/api/platforms/{id}/reactivate/` | `OBSOLETO → BORRADOR` | 200 |
| POST | `/api/platforms/{id}/image/` | Subir imagen y asignar `url_image` | 200/400/503 |
| DELETE | `/api/platforms/{id}/image/` | Quitar imagen de la ficha | 200 |
| POST | `/api/platforms/{id}/check-link/` | Verificar y registrar URL pública | 200/400 |

`status` no se modifica mediante `POST`, `PUT` o `PATCH`. Las transiciones se realizan únicamente mediante las acciones de ciclo de vida.

`url_image` es opcional. `POST /api/platforms/{id}/image/` recibe
`multipart/form-data` con el campo `image` (JPEG, PNG, GIF o WebP, máximo
5 MB por defecto), lo almacena en el bucket `imagenes` de RustFS y devuelve la
ficha con una URL pública permanente, sin expiración ni firma. Las imágenes
externas existentes, incluidas las obtenidas por cosecha, se conservan.

Cuando una plataforma eliminada se restaura, vuelve a `BORRADOR` y se limpian `validated_by` y `validated_at`.

### 5.2. Sintaxis válidas

| Método | Ruta | Uso | Respuesta habitual |
| --- | --- | --- | --- |
| GET | `/api/platforms/valid-sintaxis/` | Listar sintaxis activas | 200 |
| POST | `/api/platforms/valid-sintaxis/` | Crear sintaxis | 201 |
| GET | `/api/platforms/valid-sintaxis/{id}/` | Consultar sintaxis | 200 |
| PUT | `/api/platforms/valid-sintaxis/{id}/` | Reemplazar sintaxis | 200 |
| PATCH | `/api/platforms/valid-sintaxis/{id}/` | Actualizar parcialmente | 200 |
| DELETE | `/api/platforms/valid-sintaxis/{id}/` | Eliminar según reglas de `AuditableViewSet` | 204/200 |
| GET | `/api/platforms/valid-sintaxis/archived/` | Listar sintaxis archivadas | 200 |
| POST | `/api/platforms/valid-sintaxis/{id}/restore/` | Restaurar sintaxis archivada | 200 |

### 5.3. Historial de verificación

`LinkCheckLog` es de solo lectura para el cliente. `journal_platform = null` identifica la URL general de la plataforma; un valor no nulo identifica la URL de una revista dentro de esa plataforma. En el segundo caso, la plataforma de ambos FKs debe coincidir.

El estado visual debe interpretarse con `last_check` e `is_active`:

```text
last_check = null                         → Sin verificar
last_check != null e is_active = true    → Disponible
last_check != null e is_active = false   → Error / No disponible
```

La API expone esa interpretación directamente mediante
`verification_status`, cuyos valores son `unverified`, `available` y
`unavailable`. Un registro nuevo siempre nace con `is_active=false` y
`last_check=null`; `is_active=false` por sí solo no significa que el chequeo
haya fallado.

`http_status_code=null` no basta para determinar el estado: puede representar
una URL aún no verificada o un chequeo fallido sin respuesta HTTP. Cuando sí se
realiza un chequeo, `last_check` contiene su fecha real. `created_at` solo indica
cuándo se creó el registro.

El historial se ordena por defecto con las verificaciones realizadas primero:
`last_check` descendente con nulos al final, seguido por `created_at` e `id`
descendentes. El orden se aplica antes de la paginación. Los registros sin
verificar quedan al final y no se mezclan cronológicamente como si fueran
errores.

La selección de la URL y del estado **vigentes** usa otro criterio: toma el
evento más reciente por `created_at` e `id` descendentes. De esta forma, una
URL nueva pendiente sustituye correctamente a la URL anterior ya comprobada,
sin depender del ordenamiento de valores `NULL` de PostgreSQL.

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/api/platforms/link-check-logs/` | Listar verificaciones |
| GET | `/api/platforms/link-check-logs/{id}/` | Consultar una verificación |

El listado admite `verification_status=unverified|available|unavailable`,
además de `platform`, `journal_platform`, `journal_platform__isnull` e
`is_active`. Para distinguir una URL pendiente de una fallida debe utilizarse
`verification_status`, no solamente `is_active=false`.

No existe `POST`, `PUT`, `PATCH` ni `DELETE` público para fabricar resultados
de verificación. Registrar o cambiar `public_url` crea un registro pendiente;
`check-link` crea el registro correspondiente a una verificación real.

### 5.4. Consulta pública

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/api/platforms/public/` | Listar plataformas publicadas |
| GET | `/api/platforms/public/{id}/` | Consultar ficha pública |

Las plataformas `BORRADOR`, `OBSOLETO` o eliminadas no aparecen en este endpoint.
Una Platform puede recibir relaciones administrativas con Journals antes de
publicarse. Estas relaciones pueden preparar su clasificación derivada, pero no
alteran su estado ni sustituyen la acción explícita `publish`.

## 6. Ejemplos con `curl`

### 6.1. Crear una sintaxis válida

```bash
curl -X POST http://localhost:8000/api/platforms/valid-sintaxis/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sintaxis estándar",
    "booleans": ["AND", "OR", "NOT"],
    "parenthesis": true,
    "fields": {
      "title": "ti",
      "author": "au",
      "subject": "su",
      "issn": "is",
      "language": "la",
      "year": "yr"
    }
  }'
```

La respuesta incluye además `fields_template`.

### 6.2. Crear una plataforma de referencia sin API de cosecha

```bash
curl -X POST http://localhost:8000/api/platforms/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Repositorio institucional",
    "public_url": "https://repositorio.ejemplo.org",
    "is_harvestable": false,
    "requires_registration": false,
    "has_access_text": true,
    "valid_sintaxis": 1,
    "institutions": [1],
    "languages": [1],
    "countries": [1],
    "material_types": [1],
    "academic_programs": [1]
  }'
```

No se envía `knowledge_areas`: el backend las deriva desde los programas académicos.

### 6.3. Crear una plataforma con API y API Key

```bash
curl -X POST http://localhost:8000/api/platforms/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Plataforma con cosecha",
    "public_url": "https://www.ejemplo.org",
    "is_harvestable": true,
    "base_api_url": "https://api.ejemplo.org",
    "api_key": "clave-secreta",
    "valid_sintaxis": 1,
    "institutions": [1],
    "languages": [1],
    "countries": [1],
    "material_types": [1],
    "academic_programs": [1]
  }'
```

La clave no aparecerá en la respuesta.

### 6.4. Eliminar una API Key mediante `PATCH`

```bash
curl -X PATCH http://localhost:8000/api/platforms/1/ \
  -H "Content-Type: application/json" \
  -d '{"api_key": null}'
```

### 6.5. Registrar y verificar la URL pública

La primera verificación debe enviar la URL:

```bash
curl -X POST http://localhost:8000/api/platforms/1/check-link/ \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.ejemplo.org"}'
```

Respuesta conceptual:

```json
{
  "id": 1,
  "platform": 1,
  "url": "https://www.ejemplo.org",
  "fail_count": 0,
  "http_status_code": 200,
  "is_active": true,
  "last_check": "2026-10-05T..."
}
```

En verificaciones posteriores puede omitirse la URL y se reutiliza la última registrada:

```bash
curl -X POST http://localhost:8000/api/platforms/1/check-link/ \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 6.6. Publicar una plataforma

```bash
curl -X POST http://localhost:8000/api/platforms/1/publish/
```

Para publicarse debe estar en `BORRADOR` y cumplir las reglas de completitud, incluyendo URL pública registrada, `start_period`, `valid_sintaxis` y las relaciones activas requeridas.

No se exige `base_api_url` ni `api_key` cuando la plataforma no necesita cosecha.

### 6.7. Marcar como obsoleta

```bash
curl -X POST http://localhost:8000/api/platforms/1/mark-obsolete/
```

### 6.8. Reactivar una plataforma obsoleta

```bash
curl -X POST http://localhost:8000/api/platforms/1/reactivate/
```

La plataforma regresa a `BORRADOR` y debe validarse de nuevo antes de publicarse.

### 6.9. Consultar plataformas públicas

```bash
curl http://localhost:8000/api/platforms/public/
```

La respuesta utiliza la paginación global del proyecto:

```json
{
  "current_page": 1,
  "total_pages": 1,
  "page_size": 10,
  "total_items": 1,
  "next": null,
  "previous": null,
  "results": []
}
```

Cada elemento del listado incluye `item_number`.

## 7. Borrado lógico y restauración

Para eliminar una plataforma con relaciones de negocio, envía una explicación:

```bash
curl -X DELETE http://localhost:8000/api/platforms/1/ \
  -H "Content-Type: application/json" \
  -d '{"delete_explanation":"Plataforma retirada del repositorio"}'
```

Los registros eliminados lógicamente se consultan con:

```text
GET /api/platforms/archived/
```

Para restaurar:

```bash
curl -X POST http://localhost:8000/api/platforms/1/restore/
```

Una plataforma restaurada regresa siempre a `BORRADOR` y pierde su validación previa.

## 8. Búsqueda, ordenamiento y filtros

### 8.1. Administración

Búsqueda por nombre:

```bash
curl "http://localhost:8000/api/platforms/?search=scopus"
```

Filtros administrativos disponibles:

| Parámetro | Tipo | Ejemplo | Significado |
|---|---|---|---|
| `status` | enum | `?status=publicado` | Estado real: `borrador`, `publicado` u `obsoleto`. |
| `is_harvestable` | booleano | `?is_harvestable=true` | Indica si existe mecanismo de cosecha. |
| `requires_registration` | booleano | `?requires_registration=false` | Indica si requiere registro del usuario. |
| `has_access_text` | booleano | `?has_access_text=true` | Indica acceso a texto completo. |
| `valid_sintaxis` | entero | `?valid_sintaxis=1` | Sintaxis activa asociada. |
| `institution` | entero | `?institution=1` | Institución con relación activa. |
| `country` | entero | `?country=1` | País con relación activa. |
| `language` | entero | `?language=1` | Idioma con relación activa. |
| `knowledge_area` | entero | `?knowledge_area=1` | Área derivada activa. |
| `material_type` | entero | `?material_type=1` | Tipo de material con relación activa. |
| `academic_program` | entero | `?academic_program=1` | Programa derivado activo. |

Los valores de `status` son minúsculos y cualquier opción ajena se rechaza.
Los filtros pueden combinarse:

```bash
curl "http://localhost:8000/api/platforms/?status=publicado&country=1&is_harvestable=true"
```

Ordenamiento:

```bash
curl "http://localhost:8000/api/platforms/?ordering=name"
curl "http://localhost:8000/api/platforms/?ordering=-created_at"
```

### 8.2. Consulta pública

Filtros disponibles:

| Parámetro | Tipo | Ejemplo | Significado |
|---|---|---|---|
| `institution` | entero | `?institution=1` | Institución con relación activa. |
| `country` | entero | `?country=1` | País con relación activa. |
| `language` | entero | `?language=1` | Idioma con relación activa. |
| `knowledge_area` | entero | `?knowledge_area=1` | Área derivada activa. |
| `material_type` | entero | `?material_type=1` | Tipo de material con relación activa. |
| `academic_program` | entero | `?academic_program=1` | Programa derivado activo. |
| `requires_registration` | booleano | `?requires_registration=false` | Requisito de registro. |
| `has_access_text` | booleano | `?has_access_text=true` | Acceso a texto completo. |
| `is_harvestable` | booleano | `?is_harvestable=true` | Disponibilidad de mecanismo de cosecha. |

Ejemplos:

```bash
curl "http://localhost:8000/api/platforms/public/?country=1"
curl "http://localhost:8000/api/platforms/public/?academic_program=1"
curl "http://localhost:8000/api/platforms/public/?knowledge_area=1"
curl "http://localhost:8000/api/platforms/public/?has_access_text=true"
```

También admite búsqueda por nombre y ordenamiento por `name`, `start_period` y `finish_period`.

El endpoint público no acepta `status`: su queryset ya restringe siempre el
resultado a Platforms `PUBLICADO`. Ningún filtro adicional puede hacer visible
una Platform en `BORRADOR`, `OBSOLETO` o eliminada.

### 8.3. Historial de enlaces

Filtros:

```text
platform
journal_platform
journal_platform__isnull
is_active
```

Ordenamiento:

```text
last_check
fail_count
created_at
```

Paginación:

```text
page       → número de página
page_size  → cantidad de elementos (10 por defecto, máximo 100)
```

Ejemplo:

```bash
curl "http://localhost:8000/api/platforms/link-check-logs/?platform=1&is_active=false"
```

Para consultar únicamente el historial de la URL pública general, sin mezclar
URLs contextuales de Journals:

```bash
curl "http://localhost:8000/api/platforms/link-check-logs/?platform=1&journal_platform__isnull=true"
```

## 9. Probar sin modificar la base de datos normal

La suite de Django utiliza una base de datos de pruebas separada. Para ejecutar las pruebas de `platforms`:

```bash
docker compose -f docker/docker-compose.yml run --rm -e DJANGO_TESTING=true web python manage.py test apps.platforms --keepdb
```

Inventario actual de la suite:

```text
47 pruebas: 6 de modelos, 21 de serializadores, 7 de servicios,
2 de clasificación y 11 de API.
```

Para validar también el esquema OpenAPI:

```bash
docker compose -f docker/docker-compose.yml run --rm web python manage.py spectacular --validate --file /tmp/schema.yml
```

Resultado validado:

```text
Warnings: 0
Errors:   0
```

## 10. Errores frecuentes

| Código | Causa típica |
| --- | --- |
| 400 | API Key sin `base_api_url`, datos inválidos, publicación incompleta, URL insegura o acción de ciclo de vida no permitida |
| 404 | ID inexistente o registro eliminado |
| 405 | Método HTTP no permitido para la ruta; por ejemplo intentar escribir directamente en `link-check-logs` o `public` |
| 500 al iniciar | Dependencias, `.env` o migraciones pendientes |

Si la API no inicia, ejecuta:

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py check
```

La autenticación JWT, los permisos y la protección de escritura se implementarán en la Fase B.
# Clasificación derivada vigente

El Frontend no administra `academic_programs` ni `knowledge_areas`; ambos son
read-only. Platform los obtiene de la unión de programas de sus Journals
elegibles y de las áreas activas de esos programas:

```text
AcademicProgram ↔ KnowledgeArea       fuente de verdad
Journal ↔ AcademicProgram             fuente de verdad
Journal ↔ Platform                    fuente de verdad
Journal ↔ KnowledgeArea               derivada
Platform ↔ AcademicProgram            derivada
Platform ↔ KnowledgeArea              derivada
```

Una Journal es elegible si `deleted_at=null`, `active=true`,
`validated_at!=null` y su `SharedJournalPlatform.deleted_at=null`. Las
relaciones derivadas se conservan con Soft Delete y se restauran cuando vuelven
a ser válidas.

Una Platform sin Journals elegibles puede conservar su estado `PUBLICADO` y
clasificación vacía. Si tiene al menos una Journal elegible pero el resultado
queda sin programas o sin áreas, una Platform publicada pasa automáticamente a
`BORRADOR`, limpia su validación y deja de aparecer públicamente. Si después
recupera una clasificación completa permanece en `BORRADOR`; solo la acción
explícita `publish` puede publicarla nuevamente. Nunca se usa `OBSOLETO` para
esta invalidación.

Ejemplo de creación/edición: se envían los metadatos y relaciones no académicas
(`institutions`, `languages`, `countries`, `material_types`), pero se omiten
`academic_programs` y `knowledge_areas`.
## Contrato de URLs y verificación vigente

- `public_url` es obligatoria al crear una Platform, pero no es una columna del
  modelo: se registra como `LinkCheckLog` general (`journal_platform=null`).
- Registrar una URL no equivale a verificarla; `last_check=null` significa que
  todavía no se ha realizado una comprobación HTTP, y el registro nace con
  `is_active=false`.
- `POST /api/platforms/{id}/check-link/` verifica la URL pública vigente.
- `POST /api/platforms/{id}/check-links/` verifica secuencialmente la URL pública
  y la URL vigente de cada relación Journal-Platform no eliminada. Un fallo
  individual no detiene las demás comprobaciones.
- El historial conserva registros pendientes y resultados de verificación; el
  chequeo masivo no recorre URLs históricas ni relaciones eliminadas.

También continúa pendiente cualquier regla adicional para derivar o sincronizar
idiomas de Platform; esta fase no modifica ese comportamiento.

## Semántica de fechas del ciclo de vida

- `start_period`: fecha de registro de la plataforma. El backend la asigna al
  crearla y nunca cambia durante publish, obsolescencia, reactivación o restore.
- `finish_period`: fecha en que la plataforma fue marcada como `OBSOLETO`.
  `mark-obsolete` la asigna automáticamente; `reactivate` y restore la limpian.
- Ambos campos son de solo lectura. Enviarlos en `POST`, `PUT` o `PATCH` produce
  HTTP 400 y no modifica los valores existentes.

Etiquetas recomendadas para el Frontend:

- `start_period`: **Fecha de registro de la plataforma**.
- `finish_period`: **Fecha de obsolescencia**.

Pendiente: evaluar eliminar `Platform.start_period` y `Platform.finish_period`
si `created_at`, el estado y el historial de auditoría resultan suficientes.
# Actualización: procedencia, publicación y verificación global

## Crear no publica

`POST /api/platforms/` requiere `name` y `public_url`, permite que el resto de
la ficha permanezca incompleto y siempre conserva el estado `borrador`. La URL
queda registrada en `LinkCheckLog` para su verificación. Los demás requisitos estrictos se evalúan en
`POST /api/platforms/{id}/publish/`: URL pública vigente y verificada con un
último resultado exitoso, sintaxis vigente,
campos técnicos condicionales y al menos un valor efectivo en institución,
idioma, país, tipo de material, programa académico y área de conocimiento.
La publicación no requiere Journals asociadas ni imagen (`url_image` es
opcional).

Si la URL vigente nunca fue comprobada, `publish` indica que debe verificarse.
Si ya fue comprobada pero su último resultado falló, indica que no se encuentra
disponible y debe corregirse o verificarse nuevamente.

Cada sección administrativa se representa con `id`, `name`, `is_manual`,
`is_derived` y `editable`. Las cinco secciones compartidas con Journal se
derivan de todas las Journals activas y validadas. Para conocimiento se usa el
conjunto efectivo manual/derivado de cada Journal; una selección manual se
conserva cuando desaparece su última fuente derivada.

Los catálogos de secciones admiten filtros contextuales:
`?platform={id}&origin=manual|derived|both`, `?platform={id}&editable=true|false`
y `?available_for_platform={id}`. Este último excluye cualquier relación
vigente, independientemente de su origen.

## Sintaxis similares

`POST /api/platforms/valid-sintaxis/similar/` recibe `booleans`, `parenthesis`
y `fields`. Devuelve como máximo cinco sintaxis vigentes con similitud mínima
del 70 %, incluyendo `similarity`, `matching_fields` y `different_fields`.
Una configuración normalizada idéntica no puede crearse nuevamente; el error
incluye `existing_id`.

## Enlaces y eliminación

`POST /api/platforms/check-links/` comprueba secuencialmente todas las URLs
vigentes y responde `204` sin cuerpo. Un fallo individual no detiene los demás
chequeos. El endpoint existente por Platform conserva su respuesta detallada.

No se puede eliminar una Platform mientras exista una relación vigente con una
Journal no eliminada, incluso si la Journal está inactiva. Una ValidSintaxis en
uso por una Platform vigente tampoco puede eliminarse.

## Monitoreo automático de enlaces — 2 de noviembre de 2026

### Diagnóstico de la integración real

Todas las rutas de esta sección son relativas a la raíz del repositorio general.

| Componente | Archivos reales y responsabilidad |
| --- | --- |
| Backend | `Backend/manage.py`, `Backend/apps/`, `Backend/config/` |
| Frontend | `Frontend/package.json`, `Frontend/src/app/` — inspección sin cambios |
| Celery | `Backend/project/celery.py`, importado desde `project/__init__.py`; autodiscovery de tasks |
| Broker/cola | `Backend/config/settings.py`: `CELERY_BROKER_URL`, cola predeterminada `harvesting` |
| RabbitMQ | `RabbitMQ/Dockerfile`, `rabbitmq.conf`, `.env.example`; servicio y volumen `rabbitmq_data` en Compose |
| Worker | `docker-compose.yml`: mismo Backend, `celery -A project worker --queues=harvesting --concurrency=2` |
| Cron existente | `Cron/entrypoint.sh`, `script.sh`, `.env.example`; únicamente llama `POST /api/harvesting/schedules/run-due/`, sin credenciales |
| Correo | `Backend/apps/account/email.py`: Resend; settings `RESEND_API_KEY`, `DEFAULT_FROM_EMAIL` |
| Permisos | `Backend/apps/account/permissions.py`: `ApplicationPermission`, `has_permission`; permisos directos, presets y superadmin |
| Entorno compartido | `.env` raíz; Compose también declara `Backend/.env`, `Frontend/.env`, `RabbitMQ/.env`, `Cron/.env` por servicio |
| Documentación | `README.md` general; `Backend/context.md`, `Backend/docs/ENDPOINTS_PLATFORMS.md`, `BITACORA_PLATFORMS.md` |

Celery ya utiliza acknowledgements tardíos, reentrega ante pérdida de worker,
prefetch 1 y resultados ignorados; no hay result backend configurado. Harvesting
ya aporta un patrón de task con checkpoint y reintentos con backoff/jitter. Se
reutilizan la misma app, broker, cola, imagen y worker. No se crea un chord,
otra cola, Redis, Celery Beat ni otro scheduler. Las tasks de harvesting se
inspeccionaron para conocer el patrón y permanecen sin cambios.

La raíz compartida `.env` no reemplaza automáticamente los archivos `env_file`
de cada servicio. Infraestructura debe suministrar los archivos declarados en
Compose con valores consistentes. No se han editado secretos ni infraestructura.
En esta inspección no estaban presentes `Backend/.env`, `Frontend/.env`,
`RabbitMQ/.env` ni `Cron/.env`; sí sus ejemplos y el `.env` compartido de la raíz.

**Decisión de alcance confirmada:** se conserva el entorno por servicio y
`Backend/.env.example`, con las opciones `LINK_CHECK_BATCH_SIZE` y
`LINK_FAILURE_FRONTEND_URL`, leídas mediante `os.getenv`. El `load_dotenv()` y
la dependencia `python-dotenv` ya existían y se mantienen para no afectar posibles
ejecuciones locales fuera de Docker. El monitor no agrega otra carga de archivos
de entorno. No se centralizan variables en la raíz ni se modifica Compose con
este propósito; una eventual reorganización será un refactor independiente de
infraestructura.

### Triggers y seguridad

| Proceso | Método y ruta | Frecuencia externa | Respuesta |
| --- | --- | --- | --- |
| Total | `POST /api/platforms/check-links-async/` | Cada 4 horas | `202` |
| Confirmar fallos | `POST /api/platforms/check-failed-links/` | Cada 15 minutos | `202` |

Ambos aceptan cuerpo vacío y devuelven
`{"run_id": 123, "task_id": "uuid", "mode": "all"}` o `"mode": "failed"`.
`202` confirma el envío del coordinador a Celery, no que las comprobaciones o el
correo hayan terminado. No se espera ningún request HTTP de enlaces en la API.
Un error de publicación al broker devuelve `503` y `run_id`; una publicación
con resultado incierto puede haberse entregado. El responsable debe revisar
logs/estado persistente antes de volver a dispararla.

Requieren la autenticación existente `CookieSessionAuthentication`, CSRF en
POST y permiso efectivo **`platforms.platforms.check_link`**. No existe excepción
pública para estas rutas. `Backend/apps/platforms/permissions.py` especializa
`ApplicationPermission` únicamente para asociar las acciones propias al permiso
`check_link`; antes `check-links` podía interpretarse como `create`. Se conservan
las validaciones heredadas de sesión, cambio de contraseña y permisos efectivos.
No se modifica `account/permissions.py` ni se agrega un permiso de negocio,
token compartido o bypass de autenticación.
Los códigos de denegación son `401`/`403` según sesión, CSRF y permisos.

**Pendiente externo de autenticación de cron:** el script actual no inicia
sesión ni manda CSRF. No puede llamar estos triggers sin adaptarse. Debe usar
una cuenta administrativa dedicada con el permiso existente, completar el
cambio de contraseña si es requerido y establecer sesión por los endpoints
actuales: GET `/api/accounts/auth/csrf/`, POST `/api/accounts/auth/login/` con
email/password, cookies y `X-CSRFToken`. Tras login se debe usar el token CSRF
vigente. Las sesiones expiran tras 15 minutos sin actividad y un segundo login
reemplaza la sesión anterior; gestionar renovación/reautenticación y no compartir
la cuenta con usuarios humanos. Credenciales y cookies pertenecen al gestor de
secretos del responsable, nunca al código ni a los logs. No se ha implementado
una nueva autenticación de máquina ni se ha configurado el cron.

Se conserva el contrato síncrono `POST /api/platforms/check-links/` → `204` y
los contratos manuales por Platform: `/{id}/check-link/` → `200` con log y
`/{id}/check-links/` → `200` con resumen. El cron debe usar las rutas asíncronas.

### Selección de URLs y reglas de estado

La URL vigente es el último evento no eliminado por `created_at DESC, pk DESC`
del contexto: Platform con `journal_platform=null`, o relación Journal–Platform.
Se reutiliza `LINK_LOG_ORDERING` y la misma regla de los helpers actuales; una
subconsulta obtiene un solo evento por contexto antes de filtrar disponibilidad.
No se selecciona por `last_check`. Se excluyen logs, Platforms, Journals y
relaciones eliminados, así como relaciones de otra Platform. Se incluyen los
contextos no eliminados independientemente de su estado editorial.

Cada comprobación conserva un nuevo `LinkCheckLog`, siguiendo el historial
existente. Registrar otra URL comienza un incidente independiente con
`is_active=false`, `last_check=null`, `fail_count=0`, `failure_notified_at=null`.

| Estado | Condición |
| --- | --- |
| `unverified` | `last_check=null`; no participa en reintentos |
| `available` | Comprobado y `is_active=true`; contador 0 |
| `unavailable` | Comprobado y `is_active=false`; no implica por sí solo caída confirmada |
| Caída confirmada | URL vigente, comprobada, no disponible y `fail_count>=5` |

Cada fallo incrementa el contador consecutivo. Los fallos 1–4 se reintentan;
el quinto confirma la caída. Después no hay reintentos de 15 minutos: sigue
participando en las rondas totales de 4 horas. La detección inicial seguida de
cuatro reintentos puede confirmar una caída aproximadamente una hora después.
El primer fallo no envía correo. Los fallos 6 y posteriores conservan la marca
de notificación del incidente. Un éxito en cualquier endpoint/task establece
`is_active=true`, contador 0 y marca nula. No envía correo de recuperación;
una caída posterior puede volver a notificarse al alcanzar cinco fallos.

SSRF, estados HTTP disponibles (incluidos 401/403), timeout de 10 segundos,
redirecciones sin seguimiento y errores de transporte permanecen en el checker
existente de `services.py`. Las tasks llaman `check_link_context`, sin duplicarlo.
Una URL que deja de ser segura se bloquea sin request y registra un fallo.

### Tasks, lotes y concurrencia

`dispatch_link_checks(run_id)` planifica IDs de eventos vigentes mediante
iterator, en lotes de `LINK_CHECK_BATCH_SIZE` (50 por defecto).
`LinkCheckRun` guarda solicitante, modo y finalización; `LinkCheckBatch` guarda
los IDs y su finalización. Son tablas operativas internas, sin endpoints nuevos
de administración ni otra infraestructura. La planificación no carga todos los
objetos ni realiza HTTP. Los lotes cargan sus relaciones con `select_related`.

`check_link_batch(batch_id)` revalida elegibilidad y llama al checker por cada
contexto. Si su evento ya fue sustituido, lo omite. El checker repite esa
validación tras el request para descartar una respuesta obsoleta. Una reentrega
del lote no vuelve a incrementar un evento ya procesado. Errores inesperados
se registran por ID y permiten comprobar el resto; después se reintenta el lote
con backoff/jitter, hasta cinco reintentos. Los enlaces que responden con fallo
HTTP no provocan retry técnico de Celery: siguen el ciclo de negocio de cron.

Solo al terminar todos los lotes se encola `notify_link_failures`. Sin result
backend ni chord: la finalización se coordina por estado persistente. Un callback
repetido consulta nuevamente los candidatos no notificados. El campo interno
`LinkCheckLog.check_batch` conserva la procedencia del resultado y se propaga al
crear eventos manuales posteriores. Se excluyen de correo los resultados de
rondas todavía incompletas, incluso si otra ronda termina antes. Las rondas vacías
también permiten entregar alertas pendientes de una ronda anterior.

Los requests HTTP del checker ocurren **antes** de entrar en la transacción de
actualización. El bloqueo de la Platform estable serializa lectura del contador,
creación del evento y registro de URLs, conservando el contador de comprobaciones
manuales concurrentes. El notificador bloquea Platforms en orden de ID y relee
candidatos, de modo que dos workers no envían simultáneamente el mismo incidente.
Conserva esos locks durante el envío de correo y marca todos los candidatos solo
si el envío retorna correctamente. El rollback deja pendientes los fallidos.
Esto puede retrasar la persistencia de checks de esas Platforms mientras se envía
el correo, pero no mantiene transacciones abiertas durante sus requests de comprobación.

**Límites operativos:** una caída después de que el proveedor acepte un correo
y antes del commit puede causar repetición al reintentar; la transacción no
garantiza entrega exactamente una vez frente a esa interrupción externa. No se
ha añadido un outbox ni una garantía de idempotencia del proveedor. Un lote que
agote retries queda sin completar y la ronda no avanza a notificación; revisar
logs y reencolar el coordinador existente con ese `run_id` tras corregir el error.
Los lotes completados se omiten. Una publicación del callback fallida se reintenta
con la task del lote/coordinador; no se incorpora un scheduler de recuperación.
La cola compartida puede retrasar cosechas y checks; su capacidad corresponde
al responsable de infraestructura. Las tablas operativas requerirán una política
de retención futura si crecen de forma sostenida.

### Notificación agrupada y consulta

Destinatarios: todos los usuarios activos no eliminados con email válido y
permiso efectivo `platforms.platforms.check_link`, incluyendo permisos directos,
`AccessPreset` y superadmin. No hay lista fija. El helper de correo existente
acepta ahora `bcc` opcional; mantiene su contrato para invitaciones y contraseñas.
Las direcciones de destinatarios se ocultan en BCC, con el remitente en To.
Esta ampliación y su prueba son los únicos cambios conservados en `account`.
Su dependencia concreta es enviar un mismo resumen en una llamada del servicio
existente a varios destinatarios con privacidad: la interfaz original solo
permitía un destinatario To y no admitía BCC. Se conserva la implementación
Resend y su manejo de errores, sin modificar usuarios, presets, autenticación
ni matriz de permisos. El cambio inicial en el mapeo global de acciones se
retiró y su adaptación se trasladó a `platforms`.

Enviar copias individuales mediante la interfaz original es una alternativa,
pero requiere gestionar entregas parciales por destinatario para que un retry
no repita las copias ya aceptadas. Extraer el transporte a `core` también es
posible, pero exige coordinar la migración del servicio con su responsable;
copiar la implementación a `platforms` duplicaría el servicio existente.
La capacidad y límites de destinatarios del proveedor deben validarse en el
entorno real; no se ha ejecutado un envío.

Cada resumen incluye solo caídas vigentes todavía no notificadas: total exacto,
máximo diez entradas, número adicional omitido, nombre de Platform, tipo de
enlace, título de Journal si aplica, URL, última comprobación y fallos. Orden:
`last_check DESC, pk DESC`. Aunque se muestren diez, todos los candidatos quedan
marcados al terminar. Sin nuevas caídas o sin destinatarios no hay envío ni marca.
`EmailDeliveryError` produce reintentos Celery con backoff/jitter (máximo cinco).

`LINK_FAILURE_FRONTEND_URL` permite configurar la URL absoluta del módulo real
`/admin/alertas`; se añaden `current=true&failure_confirmed=true`. No se inventa
dominio. Si está vacía o inválida, el resumen explica que debe accederse al
módulo administrativo y que el acceso directo filtrado está pendiente. Configurar
el botón solo cuando Frontend soporte esos parámetros; hoy la vista los ignora.

Consulta completa del Backend:

`GET /api/platforms/link-check-logs/?current=true&failure_confirmed=true`

Requiere **`platforms.link-check-logs.view`**. Los destinatarios que solo tengan
`check_link` necesitarán también el permiso de consulta para usar el listado.
Se conserva la paginación (10 por defecto, máximo 100), ordering y los filtros
`platform`, `journal_platform`, `journal_platform__isnull`, `is_active`,
`verification_status`. `failure_confirmed=false` devuelve el complemento dentro
de URLs vigentes; no incluye historia. `current=true` permite consultar todos
los estados vigentes. La respuesta del log añade `failure_notified_at` nullable.
No se obliga a Frontend a reconstruir el umbral de cinco fallos.

### MENSAJE PARA RESPONSABLE DE FRONTEND

La pantalla ya existe en `/admin/alertas`:
`Frontend/src/app/admin/(panel)/alertas/page.jsx`,
`features/admin/harvesting/components/LinkAlerts.jsx` y `harvesting.js`.
Actualmente descarga el historial, agrupa únicamente por Platform, elige por
fecha de comprobación y usa un umbral de dos fallos. Todavía no ofrece la vista
completa de URLs vigentes por contexto ni interpreta los parámetros del correo.

Adaptar esa pantalla para consumir el listado paginado de
`/api/platforms/link-check-logs/?current=true&failure_confirmed=true`, respetar
`current` y `failure_confirmed` de la URL y distinguir Platform de relación
Journal–Platform. Usar `verification_status` para disponible/no disponible/sin
verificar y el filtro del Backend para caída confirmada (cinco fallos); se puede
mostrar `fail_count` como detalle. No usar `is_active=false` solo para inferir
una caída ni elegir la URL vigente por `last_check`. Mantener estados de carga,
paginación y control del permiso `platforms.link-check-logs.view`.

El correo podrá abrir esa vista filtrada al configurar su URL. El Backend realiza
la comprobación automática y no envía correo de recuperación. Frontend no
programa cron, Celery ni RabbitMQ. No se modificó ningún archivo de Frontend.

### MENSAJE PARA RESPONSABLE DE CRON / INFRAESTRUCTURA

- Total: POST `/api/platforms/check-links-async/`, cron `0 */4 * * *`.
- Reintentos: POST `/api/platforms/check-failed-links/`, cron `*/15 * * * *`.
- Ambos requieren sesión administrativa vigente, cookies, `X-CSRFToken` y
  permiso `platforms.platforms.check_link`. Preparar la cuenta dedicada y el
  flujo de login/renovación indicado arriba. El script actual sin autenticación
  no sirve para estas rutas; no copiar su excepción pública.
- Esperar `202` con `run_id`, `task_id`, `mode`; gestionar `401`/`403`/`503`.
  El script actual valida un arreglo de Harvest: debe distinguir estos objetos.
- Conservar el worker existente de Backend con autodiscovery y cola
  `harvesting`. No se necesita resultado de Celery ni otra cola/Beat.
- Variables existentes: `CELERY_BROKER_URL`, credenciales de RabbitMQ en su
  servicio, acceso a la misma BD en API/worker, `RESEND_API_KEY` y
  `DEFAULT_FROM_EMAIL`. Nuevas opciones de Backend: `LINK_CHECK_BATCH_SIZE=50`,
  `LINK_FAILURE_FRONTEND_URL` (cuando Frontend soporte filtros).
- Proporcionar los archivos `.env` por servicio declarados en Compose. La URL
  base del API y las credenciales de la cuenta cron pertenecen a infraestructura;
  no se agrega una variable de token sin un mecanismo de autenticación aprobado.
- Actualizar únicamente `Cron/entrypoint.sh`, `Cron/script.sh` y su ejemplo de
  entorno según el mecanismo elegido por su responsable. Es un pendiente externo;
  no se editaron esos archivos, RabbitMQ ni `docker-compose.yml`.
- Aplicar la migración nueva y reconstruir API/worker antes de activar llamadas.
  Cron solo dispara procesos; no implementa selección, HTTP, umbrales ni correo.

### Migración, pruebas y comandos a ejecutar por el desarrollador

No se generó ni aplicó una migración. `makemigrations platforms` debe agregar
`LinkCheckLog.failure_notified_at`, la FK interna nullable `LinkCheckLog.check_batch`
y crear `LinkCheckRun`/`LinkCheckBatch` con sus claves foráneas. No necesita
migración de datos: marcas históricas nulas
significan pendiente de notificación si la URL vigente ya tiene cinco fallos.

Desde la **raíz general** y con los archivos de entorno suministrados:

```powershell
docker compose build backend worker
docker compose run --rm --volume "${PWD}/Backend:/app" backend python manage.py makemigrations platforms --name automatic_link_monitoring
docker compose build backend worker
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py check
docker compose run --rm backend python manage.py test apps.platforms apps.account.tests.test_email apps.account.tests.test_permissions apps.account.tests.test_sessions
docker compose run --rm backend python manage.py spectacular --validate --file /tmp/schema.yaml
docker compose up -d backend worker
```

El bind mount conserva la migración generada en `Backend/` del host. La segunda
construcción la incorpora a las imágenes: Compose no monta el código como volumen.

Usar la BD PostgreSQL de pruebas con permisos para crear la base de test.
`DJANGO_TESTING=1` usa SQLite y **omite las dos pruebas reales de concurrencia**;
no es suficiente para verificar los bloqueos. Las pruebas mockean HTTP, Resend
y publicaciones Celery; no requieren ejecutar otro broker de pruebas. El worker
de aplicación sí necesita acceso al RabbitMQ existente en ejecución real.

Se añadieron pruebas en `apps/platforms/tests/test_monitoring.py` y se amplió
`apps/account/tests/test_email.py`. Incluyen selección actual, Soft Delete,
límites de retries, contador/recuperación, triggers/permisos/CSRF, chunking,
redelivery, agrupación, BCC, errores de correo y concurrencia PostgreSQL.
**Ningún comando de esta sección ni tests, Docker, Django, base de datos o Git
se ejecutó durante esta implementación.** OpenAPI, migración y entrega real
de correo están pendientes de validación por el desarrollador.

### Conventional Commits recomendados

Actualización de validación suministrada por el desarrollador: `check` sin
problemas y migración `0007` generada, aplicada y copiada al host;
suite de 116 pruebas en SQLite, 114 correctas y dos pruebas reales
de concurrencia omitidas. Estas últimas siguen pendientes en PostgreSQL.
La generación OpenAPI reportó 90 errores (17 únicos) en las APIViews de cuentas
sin serializers inferibles, 153 advertencias (38 únicas), incluidas las del
autenticador de sesión no reconocido y dos colisiones de operationId de cuentas.

Por decisión del desarrollador se retiró la extensión de OpenAPI propuesta en
`core` y su registro, conservando la implementación que pasó las pruebas. La
documentación del autenticador y de las vistas de cuentas queda fuera del alcance
actual. Usar cookies no impide documentar la API; los diagnósticos se conservan
como pendientes externos. No declarar el esquema global libre de errores.

No se ejecutó Git. Los siguientes grupos incluyen únicamente archivos editados
en esta tarea, con rutas relativas a la raíz general.

**`Feat(platforms): Implementar monitoreo asíncrono y notificación de enlaces caídos`**

Archivos:

```text
Backend/apps/platforms/models.py
Backend/apps/platforms/services.py
Backend/apps/platforms/filters.py
Backend/apps/platforms/serializers.py
Backend/apps/platforms/views.py
Backend/apps/platforms/tasks.py
Backend/apps/platforms/notifications.py
Backend/apps/platforms/permissions.py
Backend/apps/account/email.py
Backend/config/settings.py
Backend/.env.example
```

Agrupación: la coordinación, el estado, los triggers y
la notificación forman una funcionalidad integrada sobre servicios existentes.
Incluir también la migración de `platforms` **después de generarla y revisarla**;
todavía no existe un archivo nuevo de migración que pueda enumerarse.

**`Test(platforms): Validar monitoreo de enlaces y difusión de alertas`**

Archivos: `Backend/apps/platforms/tests/test_monitoring.py`,
`Backend/apps/account/tests/test_email.py`. Agrupación: cobertura del mismo flujo
de negocio y de la ampliación compatible del helper de correo.

**`Docs(platforms): Documentar monitoreo de enlaces e integración con cron`**

Archivos: `Backend/docs/ENDPOINTS_PLATFORMS.md`,
`Backend/docs/BITACORA_PLATFORMS.md`, `Backend/context.md`,
`Backend/apps/platforms/tests/PRUEBAS.md`. Agrupación: contrato, operación,
contexto, bitácora y alcance de validación de la funcionalidad.
