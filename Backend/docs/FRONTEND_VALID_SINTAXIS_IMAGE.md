# Frontend: ValidSintaxis e imágenes en Platforms y Journals

> **Regla principal:** `ValidSintaxis` no es un texto libre ni un campo de
> Platform que se escriba a mano. Es una ficha estructurada. La mayor parte de
> su interfaz debe ser **checkboxes**:
>
> - `booleans`: checkbox por operador.
> - `parenthesis`: un checkbox.
> - `fields`: checkbox por campo canónico habilitado, más un input de texto
>   opcional para el prefijo.
>
> El único valor realmente textual dentro de `ValidSintaxis` es el prefijo de
> cada entrada de `fields` (por ejemplo `"ti"` para `title`). El nombre también
> es texto, pero es el nombre de la configuración.
>
> **Decisión de arquitectura:** `ValidSintaxis` **no** debe ser un módulo de
> primer nivel en el menú administrativo. Su CRUD se abre desde el **panel de
> edición de Platform**, junto al selector `valid_sintaxis`, en un modal o
> drawer que no hace perder el formulario de la plataforma. La ruta
> `/admin/sintaxis-validas` y su entrada "Sintaxis válidas" deben retirarse del
> flujo principal.

---

## 1. Resumen ejecutivo

| Concepto | Aplica a | Endpoint | Control recomendado |
| --- | --- | --- | --- |
| CRUD de sintaxis | Platform | `/api/platforms/valid-sintaxis/` | Modal embebido en el panel de edición de Platform, con checkboxes |
| Asignar sintaxis | Platform | campo `valid_sintaxis` de `/api/platforms/` | Select simple o radios, **un solo ID entero** |
| Similitud de sintaxis | Platform | `POST /api/platforms/valid-sintaxis/similar/` | Aviso antes de guardar |
| Imagen de plataforma | Platform | `POST/DELETE /api/platforms/{id}/image/` | Input de archivo + preview |
| Imagen de revista | Journal | `POST/DELETE /api/journals/{id}/image/` | Input de archivo + preview |

### 1.1. Tipos que debe respetar el frontend

| Campo | Tipo real | UI correcta | Error típico del frontend |
| --- | --- | --- | --- |
| `name` | `string` | Input de texto | Enviarlo vacío |
| `booleans` | `array[string]` | Checkbox group | Enviar `"AND,OR,NOT"` como string |
| `parenthesis` | `boolean` | Checkbox | Enviar `"true"` / `"false"` como string |
| `fields` | `object<string, string>` | Checkbox por campo + prefijo opcional | Enviar un string o un array |
| `fields_template` | `object<string, string>` | Solo lectura | Intentar enviarlo |
| `valid_sintaxis` (Platform) | `integer \| null` | Select/radios de una sola opción | Enviar objeto, array o `""` |
| `url_image` | `string (URL) \| null` | Preview + botón de imagen | Enviar binario en JSON |

### 1.2. Aclaraciones importantes

1. **`ValidSintaxis` solo existe en Platform.** `Journal` no tiene campo
   `valid_sintaxis`. No lo envíes al crear o editar una revista: el backend no
   lo usa.
2. **Una Platform tiene una sola sintaxis.** No es un array ni un
   multi-select. El campo es una FK nullable; para publicar debe tener valor.
3. **La respuesta administrativa de Platform devuelve `valid_sintaxis` como
   ID entero.** La respuesta pública (`/api/platforms/public/`) lo devuelve
   como objeto anidado (`name`, `booleans`, `parenthesis`, `fields`), sin `id`.
   El frontend debe tolerar ambas formas al mostrar, pero al editar debe
   trabajar con el ID entero.
4. **La subida de imágenes no es un endpoint independiente.** No existe
   `/api/images/`. Se usan las acciones `image` de Platform y Journal.
5. **El cliente HTTP actual del frontend no sirve para `multipart/form-data`.**
   `apiClient.post` fuerza `Content-Type: application/json` y hace
   `JSON.stringify`. Para imágenes se necesita un helper aparte con `fetch` y
   `FormData`.

### 1.3. Dónde vive la UI de `ValidSintaxis`

La posición correcta es **dentro del panel de edición de Platform**, no como
página independiente:

```text
Panel de edición de Platform
└── Datos de la plataforma
    └── Sintaxis de búsqueda *
        ├── [ Select de sintaxis existente        ▼ ]
        ├── [ + Crear nueva sintaxis ]  → abre modal/drawer
        └── [ Editar la seleccionada ]  → abre modal/drawer
```

Reglas de esta decisión:

- El usuario **nunca pierde el formulario de Platform**: el modal se abre
  encima y, al cerrarse, el formulario conserva sus valores.
- Al guardar una sintaxis nueva, el modal se cierra y el selector de Platform
  queda apuntando al **ID recién creado**.
- Al editar la sintaxis seleccionada, se conserva el mismo ID y se refresca la
  opción del selector con el nombre actualizado.
- El modal guarda **solo `ValidSintaxis`**; no dispara el submit de Platform.
- La ruta `/admin/sintaxis-validas` y la entrada "Sintaxis válidas" del menú
  deben retirarse. Si se conserva por compatibilidad, debe ser un redirect o
  una vista secundaria fuera del menú, nunca el flujo de creación.
- El permiso `valid-sintaxis` se mantiene para habilitar los botones de
  crear/editar/eliminar dentro del modal.
- Eliminar una sintaxis desde el modal es opcional; si se ofrece, debe
  confirmar y manejar el `400` cuando esté en uso.

---

## 2. Contrato de `ValidSintaxis`

### 2.1. Modelo de datos

| Campo | Tipo | Obligatorio | Valor por defecto | Reglas |
| --- | --- | --- | --- | --- |
| `id` | entero | Solo lectura | — | — |
| `name` | string (máx. 150) | Sí | — | Se normaliza a minúsculas. Único entre registros activos, sin distinguir mayúsculas. |
| `booleans` | JSON array | No | `[]` | El backend no impone un enum. El frontend debe enviar un array de strings. |
| `parenthesis` | boolean | No | `true` en el modelo | Usar checkbox. |
| `fields` | JSON object | No | `{}` | Solo claves canónicas. Todos los valores deben ser strings. |
| `fields_template` | JSON object | Solo lectura | — | Devuelve las seis claves canónicas con valores vacíos. |
| `created_by`, `created_at`, `updated_by`, `updated_at`, `deleted_by`, `deleted_at`, `delete_explanation` | auditoría | Solo lectura | — | No enviarlos. |

Claves canónicas permitidas en `fields`:

```text
title
author
subject
issn
language
year
```

Cualquier otra clave produce HTTP 400. Los valores deben ser strings; un número
o un booleano produce HTTP 400.

### 2.2. Ejemplo de recurso

```json
{
  "id": 3,
  "name": "sintaxis estándar",
  "booleans": ["AND", "OR", "NOT"],
  "parenthesis": true,
  "fields": {
    "title": "ti",
    "author": "au",
    "subject": "su",
    "issn": "is",
    "language": "la",
    "year": "yr"
  },
  "fields_template": {
    "title": "",
    "author": "",
    "subject": "",
    "issn": "",
    "language": "",
    "year": ""
  },
  "created_by": 1,
  "created_at": "2026-11-07T12:00:00-05:00",
  "updated_by": 1,
  "updated_at": "2026-11-07T12:00:00-05:00",
  "deleted_by": null,
  "deleted_at": null,
  "delete_explanation": null
}
```

Notas:

- El backend guarda `name` en minúsculas. Si el frontend quiere mostrarlo
  capitalizado, debe hacerlo solo en la vista.
- `fields_template` es la fuente recomendada para renderizar los checkboxes de
  campos. No hardcodees la lista si puedes leerla de la respuesta.
- `booleans` no tiene validación de valores en el backend. El frontend es quien
  debe mantener la lista canónica y evitar strings sueltos.

### 2.3. Inventario de endpoints

Base: `/api/platforms/valid-sintaxis/`

| Método | Ruta | Uso | Éxito | Errores habituales |
| --- | --- | --- | --- | --- |
| `GET` | `/api/platforms/valid-sintaxis/` | Listar sintaxis activas | `200` paginado | `401`, `403` |
| `POST` | `/api/platforms/valid-sintaxis/` | Crear sintaxis | `201` | `400` |
| `GET` | `/api/platforms/valid-sintaxis/{id}/` | Consultar una sintaxis | `200` | `404` |
| `PUT` | `/api/platforms/valid-sintaxis/{id}/` | Reemplazar | `200` | `400`, `404` |
| `PATCH` | `/api/platforms/valid-sintaxis/{id}/` | Actualizar parcialmente | `200` | `400`, `404` |
| `DELETE` | `/api/platforms/valid-sintaxis/{id}/` | Eliminar | `204` o `200` | `400`, `404` |
| `GET` | `/api/platforms/valid-sintaxis/archived/` | Listar archivadas | `200` paginado | `401`, `403` |
| `POST` | `/api/platforms/valid-sintaxis/{id}/restore/` | Restaurar archivada | `200` | `404` |
| `POST` | `/api/platforms/valid-sintaxis/similar/` | Buscar configuraciones similares | `200` | `400` |

También existe un filtro de Platform por sintaxis:

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/api/platforms/?valid_sintaxis={id}` | Listar plataformas que usan esa sintaxis |

---

### 2.4. `GET /api/platforms/valid-sintaxis/`

Listado administrativo paginado.

Parámetros admitidos:

| Parámetro | Ejemplo | Uso |
| --- | --- | --- |
| `search` | `?search=estándar` | Busca por `name`. |
| `ordering` | `?ordering=name` o `?ordering=-created_at` | Ordena por `name` o `created_at`. |
| `page` | `?page=2` | Página. |
| `page_size` | `?page_size=100` | Tamaño de página; máximo 100. |

Respuesta (paginación global del proyecto):

```json
{
  "current_page": 1,
  "total_pages": 1,
  "page_size": 10,
  "total_items": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "item_number": 1,
      "id": 1,
      "name": "sintaxis estándar",
      "booleans": ["AND", "OR", "NOT"],
      "parenthesis": true,
      "fields": {"title": "ti"},
      "fields_template": {
        "title": "",
        "author": "",
        "subject": "",
        "issn": "",
        "language": "",
        "year": ""
      }
    }
  ]
}
```

Uso en frontend:

- Cargar una vez para el selector de Platform y para la pantalla de
  administración de sintaxis.
- Usar `response.results`, no asumir que la respuesta es un array.
- Para selectores, pedir `page_size=100`.
- No usar datos de ejemplo si falla la petición. Mostrar error o estado vacío.
- `item_number` solo es un número de fila; no usarlo como ID.

---

### 2.5. `POST /api/platforms/valid-sintaxis/`

Crea una sintaxis.

Request:

```json
{
  "name": "Sintaxis estándar",
  "booleans": ["AND", "OR", "NOT"],
  "parenthesis": true,
  "fields": {
    "title": "ti",
    "author": "au"
  }
}
```

Reglas:

- `name` es obligatorio.
- `booleans` debe ser un array de strings. No enviar un string separado por
  comas.
- `parenthesis` debe ser booleano.
- `fields` debe ser un objeto. Solo claves canónicas. Valores string.
- No enviar `id`, `fields_template` ni campos de auditoría.
- No es necesario enviar todas las claves de `fields`; se puede enviar un
  subconjunto.
- Enviar `"fields": {}` es válido.
- Enviar valores vacíos (`""`) es válido, pero es mejor omitir las claves no
  habilitadas.

Respuesta: `201` con el recurso creado, incluyendo `id` y `fields_template`.

Errores:

| Caso | Respuesta |
| --- | --- |
| `name` duplicado activo | `400` con `{"name": ["Ya existe un registro activo con este valor."]}` |
| Configuración idéntica a otra | `400` con `{"detail": "Ya existe una sintaxis con esta configuración.", "existing_id": 7}` |
| Clave de `fields` no permitida | `400` con mensaje que lista las claves válidas |
| Valor de `fields` no string | `400` con `"El valor de la clave 'title' debe ser una cadena de texto."` |
| `fields` no es objeto | `400` con `"El campo debe ser un objeto JSON (diccionario)."` |

Uso en frontend:

- Construir el payload desde el estado de checkboxes.
- Si el backend responde con `existing_id`, mostrar un aviso y ofrecer editar
  esa sintaxis existente.
- Si el backend responde con error de `name`, marcar el campo.

---

### 2.6. `GET /api/platforms/valid-sintaxis/{id}/`

Devuelve una sintaxis activa.

Uso en frontend:

- Cargar el formulario de edición.
- Si responde `404`, el registro fue eliminado o no existe; volver al listado.

---

### 2.7. `PUT` y `PATCH /api/platforms/valid-sintaxis/{id}/`

Actualizan una sintaxis.

- `PUT`: reemplazo completo.
- `PATCH`: actualización parcial. **Recomendado para el frontend.**

Request de ejemplo con `PATCH`:

```json
{
  "booleans": ["AND", "OR"],
  "parenthesis": false,
  "fields": {"title": "ti"}
}
```

Reglas:

- `PATCH` permite enviar solo los campos que cambian.
- Si se envía `fields`, reemplaza el objeto completo; no hace merge profundo.
- Si se envía `booleans`, reemplaza el array completo.
- La validación de configuración idéntica también aplica en actualización.
- `name` sigue siendo único.

Uso en frontend:

- Hidratar el formulario con los valores actuales.
- Enviar solo los campos modificados o el payload completo; ambos funcionan.
- Después de guardar, usar la respuesta como fuente de verdad.

---

### 2.8. `DELETE /api/platforms/valid-sintaxis/{id}/`

Elimina una sintaxis.

Comportamiento:

| Situación | Respuesta |
| --- | --- |
| Sin relaciones de negocio | `204 No Content` (borrado físico) |
| Con relaciones de negocio pero sin plataformas activas | `200` con `{"detail": "...", "permanent": false}` (borrado lógico) |
| Usada por una Platform activa | `400` con `{"detail": "No se puede eliminar el registro porque está siendo utilizado por otros registros vigentes."}` |
| Con relaciones que exigen explicación | `400` pidiendo `delete_explanation` |

> **Importante:** el endpoint puede pedir `delete_explanation` si la sintaxis
> está referenciada por registros históricos (por ejemplo, plataformas
> archivadas). El frontend actual llama `deleteValidSintaxis(id)` sin cuerpo.
> Si aparece ese `400`, hay que mostrar un modal para pedir la explicación y
> reintentar con `{ "delete_explanation": "..." }`.

Uso en frontend:

- Confirmar antes de eliminar.
- Manejar `204` y `200`.
- Si `400`, mostrar el `detail` y, si aplica, pedir explicación.
- Después de eliminar, recargar el listado.

---

### 2.9. `GET /api/platforms/valid-sintaxis/archived/`

Lista sintaxis eliminadas lógicamente. Misma paginación y parámetros de
búsqueda/ordenamiento que el listado activo.

Uso en frontend:

- Pestaña o vista de archivados.
- Mostrar acciones de restaurar.

---

### 2.10. `POST /api/platforms/valid-sintaxis/{id}/restore/`

Restaura una sintaxis archivada.

- Request: cuerpo vacío `{}`.
- Respuesta: `200` con el recurso restaurado.
- `404` si no existe una sintaxis eliminada con ese ID.

Uso en frontend:

- Llamar desde la vista de archivados.
- Recargar el listado activo después de restaurar.

---

### 2.11. `POST /api/platforms/valid-sintaxis/similar/`

Busca configuraciones vigentes parecidas antes de crear o actualizar.

Request:

```json
{
  "booleans": ["AND", "OR", "NOT"],
  "parenthesis": true,
  "fields": {
    "title": "ti",
    "author": "au"
  }
}
```

Los tres campos son obligatorios. `fields` debe ser un objeto de strings y
respetar las claves canónicas.

Respuesta:

```json
{
  "results": [
    {
      "id": 7,
      "name": "sintaxis estándar",
      "similarity": 85,
      "matching_fields": ["booleans", "parenthesis", "fields.title"],
      "different_fields": ["fields.author"]
    }
  ]
}
```

Reglas:

- Devuelve como máximo **5** resultados.
- Solo devuelve resultados con similitud **>= 70**.
- La similitud se calcula sobre `booleans`, `parenthesis` y cada clave de
  `fields` que tenga valor en alguna de las dos configuraciones.
- `matching_fields` y `different_fields` usan la notación `fields.<clave>`.
- Una configuración idéntica da `similarity: 100`.

Uso en frontend:

- Llamar antes de crear (opcionalmente antes de editar).
- Si hay resultados, mostrar un modal con nombre, porcentaje y campos
  coincidentes/diferentes.
- Permitir "Crear de todas formas".
- No usar `result` como array directo: la forma estable es `result.results`.
- Si el backend rechaza la creación por configuración idéntica, usar
  `existing_id` para ofrecer editar el registro existente.

---

### 2.12. Filtro de plataformas por sintaxis

```http
GET /api/platforms/?valid_sintaxis=3
```

Devuelve plataformas cuya FK apunta a esa sintaxis y que no está eliminada.

Uso en frontend:

- Filtro del listado administrativo de plataformas.
- No confundir con el listado de sintaxis.

---

## 3. Implementación de `ValidSintaxis` en el frontend

### 3.1. Estado recomendado

```js
const emptySyntaxForm = {
  name: "",
  booleans: [],       // array de strings, no string
  parenthesis: false, // boolean, no "true"/"false"
  fields: {},         // solo claves habilitadas; valores string
};

// Opcional para la UI:
const [enabledFields, setEnabledFields] = useState([]);
const [fieldPrefixes, setFieldPrefixes] = useState({});
```

También puedes manejar `fields` directamente y usar la presencia de la clave
para saber si el campo está habilitado:

```js
const fields = {
  title: "ti",
  author: "au",
};
// "title" y "author" están habilitados; las demás claves no existen.
```

### 3.2. Checkboxes de operadores booleanos

Lista canónica recomendada por la documentación del backend:

```js
const BOOLEAN_OPERATORS = ["AND", "OR", "NOT"];
```

Si el negocio confirma que la plataforma también admite otros operadores,
puedes ampliar la lista (por ejemplo `XOR`, `NAND`, `NOR`). Lo importante es
que la lista viva en una sola constante y que el payload siempre sea un array.

```jsx
<fieldset>
  <legend>Operadores booleanos</legend>
  {BOOLEAN_OPERATORS.map((operator) => (
    <label key={operator}>
      <input
        type="checkbox"
        checked={form.booleans.includes(operator)}
        onChange={(event) => {
          setForm((current) => ({
            ...current,
            booleans: event.target.checked
              ? [...current.booleans, operator]
              : current.booleans.filter((value) => value !== operator),
          }));
        }}
      />
      {operator}
    </label>
  ))}
</fieldset>
```

No uses:

- Un input de texto con `"AND, OR, NOT"`.
- Un `<select multiple>` que devuelva strings separados.
- Un único checkbox llamado "booleanos".

### 3.3. Checkbox de paréntesis

```jsx
<label>
  <input
    type="checkbox"
    checked={form.parenthesis}
    onChange={(event) =>
      setForm((current) => ({
        ...current,
        parenthesis: event.target.checked,
      }))
    }
  />
  Admite paréntesis
</label>
```

### 3.4. Checkboxes de campos + prefijo

La UI correcta no es "seis inputs de texto". Es:

```text
Campos admitidos
[x] title     Prefijo: [ti]
[x] author    Prefijo: [au]
[ ] subject   Prefijo: [  ]
[ ] issn      Prefijo: [  ]
[ ] language  Prefijo: [  ]
[ ] year      Prefijo: [  ]
```

Reglas:

- Las claves se obtienen de `fields_template` (o de una constante compartida).
- El checkbox indica si el campo está soportado.
- El input de prefijo solo se muestra/habilita cuando el checkbox está activo.
- Al desmarcar, se elimina la clave de `fields`.
- Al marcar, se agrega la clave con el prefijo actual (puede ser `""`).
- Si el prefijo queda vacío, se puede omitir la clave del payload o enviar
  `""`. Recomendación: omitirla para no ensuciar la configuración y para que
  la similitud no la considere.

Ejemplo de payload resultante:

```json
{
  "name": "Sintaxis estándar",
  "booleans": ["AND", "OR"],
  "parenthesis": true,
  "fields": {
    "title": "ti",
    "author": "au"
  }
}
```

### 3.5. Constructor de payload

```js
function buildSyntaxPayload(form) {
  const fields = Object.fromEntries(
    Object.entries(form.fields).filter(
      ([, prefix]) => typeof prefix === "string" && prefix.trim() !== ""
    )
  );

  return {
    name: form.name.trim(),
    booleans: [...form.booleans],
    parenthesis: Boolean(form.parenthesis),
    fields,
  };
}
```

Si quieres conservar claves con prefijo vacío, cambia el filtro por:

```js
Object.entries(form.fields)
```

Pero no envíes valores que no sean strings.

### 3.6. Hidratación al editar

```js
function syntaxToForm(item) {
  return {
    name: item.name ?? "",
    booleans: Array.isArray(item.booleans)
      ? item.booleans.map((value) => String(value))
      : [],
    parenthesis: Boolean(item.parenthesis),
    fields: Object.fromEntries(
      Object.entries(item.fields ?? {}).filter(
        ([, value]) => typeof value === "string" && value !== ""
      )
    ),
  };
}
```

No filtres los operadores contra una lista cerrada al hidratar. Si el backend
alguna vez devuelve un operador que el frontend no conoce, filtrarlo lo
eliminaría silenciosamente al guardar. Mejor:

- Mostrar los operadores conocidos como checkboxes.
- Mostrar los desconocidos como chips de solo lectura o agregarlos a la lista
  de opciones.
- Si se edita otro campo, conservar los operadores desconocidos en el array.

### 3.7. Flujo de creación con similitud

```text
1. Usuario completa nombre + checkboxes en el modal abierto desde el panel de
   Platform.
2. Validar nombre.
3. POST /api/platforms/valid-sintaxis/similar/
4. Si results.length > 0:
   - mostrar modal con similitud;
   - permitir cancelar o "crear de todas formas".
5. POST /api/platforms/valid-sintaxis/
6. Si 400 con existing_id:
   - mostrar aviso;
   - ofrecer editar el registro existente.
7. Al guardar, cerrar el modal, refrescar el catálogo y seleccionar el nuevo ID
   en `formData.valid_sintaxis` sin recargar la página.
```

### 3.8. Flujo de edición

```text
1. GET /api/platforms/valid-sintaxis/{id}/
2. Hidratar el modal de edición.
3. PATCH /api/platforms/valid-sintaxis/{id}/
4. Usar la respuesta como fuente de verdad.
5. Actualizar la opción del selector en memoria y conservar el mismo ID.
```

### 3.9. Integración en el panel de edición de Platform

El campo `valid_sintaxis` de Platform es una sola FK entera. La gestión de las
sintaxis ocurre **en el mismo panel de edición**, no en un módulo aparte.

#### 3.9.1. Selector + acciones

```text
Sintaxis de búsqueda *
[ Seleccione una sintaxis        ▼ ]
[ + Crear nueva sintaxis ]  [ Editar ]
```

```jsx
<div>
  <label htmlFor="valid_sintaxis">Sintaxis de búsqueda *</label>

  <select
    id="valid_sintaxis"
    value={formData.valid_sintaxis ?? ""}
    onChange={(event) =>
      setFormData((current) => ({
        ...current,
        valid_sintaxis: event.target.value
          ? Number(event.target.value)
          : null,
      }))
    }
  >
    <option value="">Seleccione una sintaxis</option>
    {syntaxOptions.map((syntax) => (
      <option key={syntax.id} value={syntax.id}>
        {syntax.name}
      </option>
    ))}
  </select>

  <button type="button" onClick={() => setSyntaxModal({ mode: "create" })}>
    + Crear nueva sintaxis
  </button>

  <button
    type="button"
    disabled={!formData.valid_sintaxis}
    onClick={() =>
      setSyntaxModal({
        mode: "edit",
        item: syntaxOptions.find(
          (syntax) => syntax.id === Number(formData.valid_sintaxis)
        ),
      })
    }
  >
    Editar
  </button>
</div>
```

Reglas:

- Guardar el valor como número o `null`, no como string persistente.
- No seleccionar automáticamente la primera sintaxis.
- No usar `1` como fallback.
- No enviar un objeto `{ id, name }`; enviar solo el ID.
- En creación de borrador se puede enviar `null` u omitir.
- Para publicar, el backend exige una sintaxis válida. Si es `null`, el
  checklist de publicación debe impedir el botón o mostrar el error.
- Si el catálogo está vacío, mostrar "No hay sintaxis configuradas" y un botón
  **"Crear la primera sintaxis"** que abra el modal. No inventar datos ni
  navegar a otra página.
- No usar `/admin/sintaxis-validas` como destino del enlace.

#### 3.9.2. Modal/drawer embebido

El formulario de sintaxis (secciones 3.1 a 3.6) se monta en un modal o drawer
sobre el panel de Platform:

```jsx
const [syntaxModal, setSyntaxModal] = useState(null);
// null | { mode: "create" } | { mode: "edit", item }

{syntaxModal && (
  <ValidSintaxisModal
    mode={syntaxModal.mode}
    item={syntaxModal.item}
    onClose={() => setSyntaxModal(null)}
    onSaved={(saved) => {
      setSyntaxOptions((current) => {
        const exists = current.some((syntax) => syntax.id === saved.id);
        return exists
          ? current.map((syntax) =>
              syntax.id === saved.id ? saved : syntax
            )
          : [...current, saved];
      });
      setFormData((current) => ({
        ...current,
        valid_sintaxis: saved.id,
      }));
      setSyntaxModal(null);
    }}
  />
)}
```

Comportamiento esperado:

- **Crear:** `similar` → `POST` → `onSaved(newItem)`. El selector de Platform
  queda con el ID nuevo.
- **Editar:** `PATCH` → `onSaved(updatedItem)`. El selector conserva el mismo
  ID y actualiza el texto de la opción.
- **Eliminar (opcional):** `DELETE`; si el backend responde `400`, mostrar el
  motivo y no cerrar el modal.
- **Cerrar sin guardar:** no cambia la selección ni el catálogo.
- El modal no dispara el submit del formulario de Platform.

#### 3.9.3. Reglas de estado

- El formulario de Platform puede estar "sucio" cuando se abre el modal; al
  cerrarlo, esos valores deben seguir intactos.
- Crear una sintaxis es una operación independiente: si después falla el
  `POST/PATCH` de Platform, la sintaxis ya existe. Conviene avisarlo o
  reutilizarla en el siguiente intento.
- Refrescar el catálogo después de crear/editar para que el selector muestre
  el nombre actualizado.
- Si el usuario no tiene permiso `valid-sintaxis`, ocultar los botones de
  crear/editar, pero permitir seleccionar una sintaxis existente.

#### 3.9.4. Visualización

- Respuesta administrativa: `valid_sintaxis` es un entero. Buscar el nombre en
  el catálogo.
- Respuesta pública: `valid_sintaxis` es un objeto con `name`, `booleans`,
  `parenthesis` y `fields`. Mostrar `valid_sintaxis.name`.
- Si no hay sintaxis: mostrar **"Sin sintaxis"**, no "Sintaxis estándar".

#### 3.9.5. Retiro del módulo independiente

Archivos de referencia para la migración (no se modifican en esta guía):

| Archivo | Acción |
| --- | --- |
| `Frontend/src/app/admin/(panel)/sintaxis-validas/page.jsx` | Eliminar o convertir en redirect; no debe ser el flujo de creación. |
| `Frontend/src/shared/layouts/AdminLayout.jsx` | Quitar la entrada "Sintaxis válidas" del menú. |
| `Frontend/src/features/admin/sintaxis/components/ValidSintaxisManager.jsx` | Reutilizar su formulario como `ValidSintaxisModal` embebido, no como página. |
| `Frontend/src/shared/components/UserPermissionMatrix.jsx` | Conservar el permiso `valid-sintaxis` para las acciones del modal. |

### 3.10. Problemas detectados en el frontend actual

| Archivo | Problema | Corrección recomendada |
| --- | --- | --- |
| `Frontend/src/app/admin/(panel)/sintaxis-validas/page.jsx` y `AdminLayout.jsx` | `ValidSintaxis` está como módulo de primer nivel ("Sintaxis válidas"), separado del panel de Platform. | Retirar la ruta y la entrada del menú; abrir el formulario como modal desde el selector de Platform. |
| `Frontend/src/features/admin/sintaxis/components/ValidSintaxisManager.jsx` | La sección "Campos y sintaxis" renderiza seis inputs de texto y envía siempre las seis claves, incluso vacías. | Reemplazar por checkbox por campo + prefijo opcional; enviar solo claves habilitadas. |
| `ValidSintaxisManager.jsx` | Al hidratar, filtra `booleans` contra `BOOLEAN_OPTIONS`, por lo que puede borrar operadores desconocidos al guardar. | Conservar todos los valores; mostrar los conocidos y preservar los demás. |
| `ValidSintaxisManager.jsx` | El manejo de la respuesta de `similar` prueba varias formas (`result`, `results`, `similarities`, `similarity`). | Usar la forma estable `response.results`. |
| `Frontend/src/features/admin/databases/services/platformService.js` | `getValidSintaxis()` devuelve sintaxis falsas (`id: 1`, `id: 2`, `id: 3`) si falla la petición. | Eliminar el fallback; propagar el error y mostrar estado vacío/error. |
| `platformService.js` | `getValidSintaxis()` y `getValidSintaxisList()` no piden `page_size` y no manejan bien el error. | Pedir `page_size=100` para selectores; manejar error explícitamente. |
| `Frontend/src/features/admin/databases/components/DatabaseForm.jsx` | `valid_sintaxis` inicia como `""` y, al crear, se autoselecciona `catData.sintaxis[0]?.id || 1`. | Iniciar en `null`; no autoseleccionar; no usar `1` como fallback. |
| `DatabaseForm.jsx` | El `<select>` no tiene opción vacía ni muestra error de `valid_sintaxis`. | Agregar `<option value="">Seleccione una sintaxis</option>` y mensaje de error. |
| `Frontend/src/features/admin/databases/components/DatabaseDetail.jsx` | Si no encuentra la sintaxis, muestra "Sintaxis estándar". | Mostrar "Sin sintaxis" y reflejar que falta para publicar. |
| `DatabaseForm.jsx` y `Frontend/src/features/admin/journals/components/JournalForm.jsx` | `url_image` es un input de texto, no usan el endpoint de imagen. | Ver sección 5. |
| `Frontend/src/features/admin/journals/components/JournalForm.jsx` | Envía `knowledge_areas` en el payload, aunque el backend lo ignora. | Quitarlo del payload. |
| `Frontend/src/features/admin/journals/services/journalService.js` | `createJournal` y `patchJournal` transforman y envían `knowledge_areas`. | Quitarlo; el backend deriva las áreas de `academic_programs`. |

> El problema de "esperar strings" se ve en dos lugares:
>
> 1. `ValidSintaxisManager` trata `fields` como seis strings libres, cuando
>    debería ser una selección de campos (checkbox) más un prefijo opcional.
> 2. El formulario de Platform maneja `valid_sintaxis` como string de `<select>`
>    y lo convierte a número al final; es aceptable como estado transitorio,
>    pero el contrato es un ID entero y no debe haber defaults inventados.
>
> `booleans` y `parenthesis` **nunca** deben ser strings.

---

## 4. Servicio de imágenes

### 4.1. Qué es

El "servicio de imágenes" no tiene una URL propia. Es una acción compartida
(`ResourceImageMixin`) que existe en:

- `PlatformViewSet`: `/api/platforms/{id}/image/`
- `JournalViewSet`: `/api/journals/{id}/image/`

Características:

| Aspecto | Comportamiento |
| --- | --- |
| Almacenamiento | RustFS (compatible con S3), bucket configurado en `S3_BUCKET` (por defecto `imagenes`). |
| Carpeta Platform | `platforms/` |
| Carpeta Journal | `journals/` |
| Nombre del archivo | UUID + extensión; no se usa el nombre original. |
| Formatos | JPEG, PNG, GIF, WebP. |
| Validación | Por firma binaria real, no por nombre ni `Content-Type` del cliente. |
| Tamaño máximo | `S3_MAX_IMAGE_SIZE`; por defecto **5 MB**. |
| URL resultante | Pública, permanente, sin expiración ni firma. |
| Campo multipart | `image` |
| Respuesta | El recurso completo (`PlatformSerializer` o `JournalSerializer`), no un objeto de imagen. |
| GET de imagen | No existe. La URL se lee de `url_image` en el recurso. |
| Borrado | Si la URL fue subida por este backend, se elimina de RustFS. Si es externa, solo se desasocia. |

### 4.2. Relación con `url_image`

`url_image` sigue siendo un campo URL escribible en el CRUD normal de Platform
y Journal. Eso permite:

- Guardar una URL externa (por ejemplo, una imagen obtenida por cosecha).
- Migrar datos existentes.

Pero para imágenes subidas desde el panel, el flujo recomendado es:

```text
POST /api/platforms/{id}/image/   (multipart, campo image)
DELETE /api/platforms/{id}/image/ (quitar)
```

No uses `PATCH` con `url_image: null` para "quitar" una imagen subida: eso
desasocia la URL pero **no** elimina el objeto de RustFS. Para eliminar el
archivo administrado, usa `DELETE /image/`.

### 4.3. Inventario de endpoints de imagen

| Método | Ruta | Uso | Éxito | Errores |
| --- | --- | --- | --- | --- |
| `POST` | `/api/platforms/{id}/image/` | Subir o reemplazar imagen de Platform | `200` con Platform | `400`, `404`, `503` |
| `DELETE` | `/api/platforms/{id}/image/` | Quitar imagen de Platform | `200` con Platform | `404` |
| `POST` | `/api/journals/{id}/image/` | Subir o reemplazar imagen de Journal | `200` con Journal | `400`, `404`, `503` |
| `DELETE` | `/api/journals/{id}/image/` | Quitar imagen de Journal | `200` con Journal | `404` |

No hay `GET`, `PUT` ni `PATCH` para estas rutas.

---

### 4.4. `POST /api/platforms/{id}/image/`

Sube o reemplaza la imagen de una plataforma.

Request:

```http
POST /api/platforms/10/image/
Content-Type: multipart/form-data; boundary=...
```

Campo:

```text
image: <archivo>
```

No envíes `url_image`, `platform`, `name` ni otros campos. Solo `image`.

Respuesta `200`:

```json
{
  "id": 10,
  "name": "repositorio institucional",
  "url_image": "http://localhost:9000/imagenes/platforms/7f3c...png",
  "valid_sintaxis": 3,
  "...": "resto de la ficha"
}
```

Comportamiento:

- Si la plataforma ya tenía una imagen administrada por el backend, se elimina
  de RustFS después de guardar la nueva.
- Si la plataforma tenía una URL externa, solo se desasocia; no se intenta
  borrar el archivo externo.
- Si la actualización de la ficha falla después de subir, el backend intenta
  eliminar el archivo recién subido.
- La imagen es opcional para crear/publicar una plataforma.

Errores:

| Caso | Respuesta |
| --- | --- |
| Archivo vacío | `400` con `{"image": ["El archivo de imagen está vacío."]}` |
| Archivo demasiado grande | `400` con `{"image": ["La imagen supera el tamaño máximo permitido (5 MB)."]}` |
| Firma no reconocida | `400` con `{"image": ["El archivo no es una imagen válida. Formatos admitidos: JPEG, PNG, GIF y WebP."]}` |
| Formato no permitido por configuración | `400` con `{"image": ["El formato ... no está permitido."]}` |
| Falta el campo `image` | `400` con error de campo requerido |
| Content-Type no multipart | `415` |
| Platform inexistente/eliminada | `404` |
| RustFS no configurado o error de subida | `503` con `{"image": ["..."]}` |

---

### 4.5. `DELETE /api/platforms/{id}/image/`

Quita la imagen de la plataforma.

- Request: sin cuerpo.
- Respuesta: `200` con la ficha y `"url_image": null`.
- Si la URL era administrada por el backend, se elimina de RustFS.
- Si la URL era externa, solo se desasocia.
- Si no había imagen, la operación es idempotente y responde `200`.
- `404` si la plataforma no existe o está eliminada.

---

### 4.6. `POST` y `DELETE /api/journals/{id}/image/`

Tienen exactamente el mismo contrato que las rutas de Platform, pero:

- Carpeta de almacenamiento: `journals/`.
- Respuesta: `JournalSerializer`.
- La revista debe existir y no estar eliminada.
- La imagen es opcional para crear/publicar una revista.

Ejemplo de respuesta:

```json
{
  "id": 7,
  "issn": "1476-4687",
  "title": "nature",
  "url_image": "http://localhost:9000/imagenes/journals/2b9d...webp",
  "...": "resto de la ficha"
}
```

---

## 5. Implementación de imágenes en el frontend

### 5.1. Flujo recomendado

Para una ficha nueva:

```text
1. POST /api/platforms/   (JSON, sin archivo)
2. Tomar el id de la respuesta.
3. POST /api/platforms/{id}/image/  (multipart, campo image)
4. Actualizar el estado con url_image de la respuesta.
```

Para una ficha existente:

```text
1. POST /api/platforms/{id}/image/  (subir/reemplazar)
2. Actualizar el estado con url_image de la respuesta.
```

No intentes meter el archivo en el `POST` JSON de creación. El serializer de
Platform/Journal no acepta binarios.

Alternativa para fichas nuevas: guardar primero como borrador, subir la imagen
y luego continuar. Si el usuario cancela después de subir, la imagen queda
asociada al borrador; eso es aceptable y se puede reemplazar o eliminar.

### 5.2. Limitación del `apiClient` actual

`Frontend/src/shared/services/apiClient.js` hace esto en `post`:

```js
headers: { "Content-Type": "application/json", ... }
body: JSON.stringify(body)
```

Por eso **no puedes usar `apiClient.post` con `FormData`**. Necesitas un helper
dedicado. Ejemplo con `fetch`:

```js
function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

async function uploadResourceImage(resource, id, file) {
  const formData = new FormData();
  formData.append("image", file);

  const csrfToken = getCsrfToken();
  const response = await fetch(`/api/${resource}/${id}/image/`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      // No agregar Content-Type: el navegador pone el boundary.
    },
    body: formData,
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const error = new Error(
      data?.image?.[0] || data?.detail || "No se pudo subir la imagen."
    );
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

async function deleteResourceImage(resource, id) {
  const csrfToken = getCsrfToken();
  const response = await fetch(`/api/${resource}/${id}/image/`, {
    method: "DELETE",
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const error = new Error(
      data?.detail || "No se pudo quitar la imagen."
    );
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}
```

Puedes agregar estos métodos a `platformService` y `journalService`, pero deben
usar `fetch`/`FormData` y no `apiClient.post`.

### 5.3. Input de archivo

```jsx
<input
  type="file"
  accept="image/jpeg,image/png,image/gif,image/webp"
  onChange={(event) => {
    const file = event.target.files?.[0];
    if (file) handleImageSelected(file);
  }}
/>
```

Validaciones recomendadas en cliente:

- Tipo MIME dentro de `image/jpeg`, `image/png`, `image/gif`, `image/webp`.
- Tamaño <= 5 MB (o el valor configurado; el backend siempre valida).
- Mostrar el nombre y el tamaño.
- Deshabilitar el botón mientras se sube.
- Mostrar spinner/progreso.

No confíes solo en la extensión: el backend valida la firma binaria. Si el
archivo no es una imagen real, devolverá `400`.

### 5.4. Preview

```jsx
const [previewUrl, setPreviewUrl] = useState(platform.url_image || null);

function handleImageSelected(file) {
  const objectUrl = URL.createObjectURL(file);
  setPreviewUrl(objectUrl);
  // Recuerda revocar el objeto cuando se reemplace o desmonte:
  // URL.revokeObjectURL(objectUrl);
}
```

Para mostrar la imagen guardada:

```jsx
{previewUrl ? (
  <img
    src={previewUrl}
    alt={`Imagen de ${platform.name}`}
    className="h-24 w-24 rounded-lg object-cover"
  />
) : (
  <div className="h-24 w-24 rounded-lg bg-slate-100 text-xs text-slate-400">
    Sin imagen
  </div>
)}
```

Maneja `onError` para mostrar el placeholder si la URL externa está rota.

### 5.5. Después de la respuesta

La respuesta del endpoint de imagen es la ficha completa. Usa su `url_image`:

```js
const updated = await uploadResourceImage("platforms", platformId, file);
setPlatform(updated);
setFormData((current) => ({
  ...current,
  url_image: updated.url_image ?? "",
}));
```

No vuelvas a enviar `url_image` en el siguiente `PATCH` si no cambió. Si lo
envías con el mismo valor, no pasa nada, pero es redundante.

### 5.6. Quitar imagen

```js
const updated = await deleteResourceImage("platforms", platformId);
setPlatform(updated); // url_image === null
```

No uses `PATCH { url_image: null }` para imágenes administradas: deja el
archivo huérfano en RustFS.

### 5.7. Errores y estados

| Código | Causa | UI |
| --- | --- | --- |
| `400` | Archivo inválido, vacío o demasiado grande | Mostrar mensaje bajo el input. |
| `404` | Ficha inexistente/eliminada | Volver al listado. |
| `401` | Sesión expirada | Redirigir a login. |
| `403` | Sin permiso de actualización | Mostrar "No autorizado". |
| `415` | Content-Type incorrecto | Revisar que se esté usando `FormData`. |
| `503` | RustFS no disponible | Mostrar "Servicio de imágenes no disponible" y permitir reintentar. |

### 5.8. Problemas detectados en el frontend actual

| Archivo | Problema | Corrección recomendada |
| --- | --- | --- |
| `Frontend/src/features/admin/databases/components/DatabaseForm.jsx` | `url_image` es un input de texto (`type="url"`). | Reemplazar por input de archivo + preview + POST `/image/`. |
| `Frontend/src/features/admin/journals/components/JournalForm.jsx` | `url_image` es un input de texto. | Igual: input de archivo + POST `/image/`. |
| `Frontend/src/features/admin/journals/components/JournalDetail.jsx` | Muestra `url_image` como enlace de texto. | Mostrar `<img>` con fallback y botón de reemplazo/eliminación. |
| `Frontend/src/features/admin/databases/components/DatabaseDetail.jsx` | No muestra la imagen de la plataforma. | Agregar bloque de imagen con `url_image`. |
| `Frontend/src/shared/services/apiClient.js` | `post` fuerza JSON y no acepta `FormData`. | Crear helper `uploadResourceImage` con `fetch`, o extender el cliente para detectar `FormData`. |
| `Frontend/src/features/admin/databases/services/platformService.js` | No existe método de imagen. | Agregar `uploadPlatformImage` / `deletePlatformImage`. |
| `Frontend/src/features/admin/journals/services/journalService.js` | No existe método de imagen. | Agregar `uploadJournalImage` / `deleteJournalImage`. |

---

## 6. Dónde encajan estos servicios en los flujos de Platform y Journal

### 6.1. Platform

Campos relevantes para esta guía:

```text
name
public_url
valid_sintaxis      ← FK entera, nullable en borrador, obligatoria para publicar
url_image           ← URL; preferir POST/DELETE /image/
```

Flujo:

```text
1. Cargar catálogos, incluyendo GET /api/platforms/valid-sintaxis/?page_size=100.
2. Usuario elige una sintaxis (select/radios), la crea desde el botón
   "Crear nueva" (modal embebido) o deja null en borrador.
3. Guardar:
   POST /api/platforms/  o  PATCH /api/platforms/{id}/
   body.valid_sintaxis = id entero o null
4. Si hay archivo:
   POST /api/platforms/{id}/image/  (multipart, campo image)
5. Verificar URL:
   POST /api/platforms/{id}/check-link/
6. Publicar:
   POST /api/platforms/{id}/publish/
7. Si 400 por valid_sintaxis, resaltar el selector y volver al formulario.
```

Checklist de publicación relacionado:

- [ ] `valid_sintaxis` seleccionada (no null).
- [ ] URL pública registrada y verificada.
- [ ] Institución, país, idioma y tipo de material.
- [ ] Si `is_harvestable=true`, `base_api_url`.
- [ ] La imagen **no** es obligatoria.

### 6.2. Journal

Campos relevantes:

```text
url_image   ← URL; preferir POST/DELETE /image/
```

`Journal` **no** tiene `valid_sintaxis`. No lo envíes.

Flujo:

```text
1. Cargar catálogos.
2. Guardar:
   POST /api/journals/  o  PATCH /api/journals/{id}/
3. Si hay archivo:
   POST /api/journals/{id}/image/  (multipart, campo image)
4. Publicar:
   POST /api/journals/{id}/publish/
```

La imagen no es obligatoria para publicar una revista.

---

## 7. Matriz de componentes recomendada

| Componente | Responsabilidad |
| --- | --- |
| `SyntaxSelector` (en `DatabaseForm`) | Select/radios + botones "Crear nueva" y "Editar"; mantiene el ID entero. |
| `ValidSintaxisModal` | Formulario embebido con checkboxes, similitud y errores; crea/edita sin salir del panel. |
| `SyntaxFieldsEditor` | Checkbox por campo canónico + prefijo opcional. |
| `ResourceImageUploader` | Input de archivo, preview, POST/DELETE `/image/`, errores. |
| `platformService` | CRUD, sintaxis, imagen de Platform. |
| `journalService` | CRUD, imagen de Journal. |
| `apiClient` | JSON normal; el uploader usa `fetch`/`FormData`. |

> No debe existir una página de `ValidSintaxis` como módulo de primer nivel.
> El CRUD se expone desde el panel de edición de Platform.

---

## 8. Checklist de aceptación

### ValidSintaxis

- [ ] No existe una entrada "Sintaxis válidas" en el menú.
- [ ] `/admin/sintaxis-validas` no es el flujo de creación (eliminada o redirect).
- [ ] Desde el panel de edición de Platform se puede crear una sintaxis sin
      salir de la página.
- [ ] Al crear una sintaxis, el selector de Platform queda con el ID nuevo.
- [ ] Al editar, el selector conserva el mismo ID y muestra el nombre
      actualizado.
- [ ] Cerrar el modal sin guardar no altera el formulario de Platform ni la
      selección.
- [ ] El modal guarda solo `ValidSintaxis`, no el Platform.
- [ ] Si el modal incluye listado, usa `response.results`.
- [ ] El formulario de sintaxis usa checkboxes para `booleans`.
- [ ] El formulario de sintaxis usa un checkbox para `parenthesis`.
- [ ] Los campos de `fields` se seleccionan con checkbox, no con seis inputs
      libres.
- [ ] El prefijo de cada campo se envía como string.
- [ ] El payload no incluye `fields_template`, `id` ni auditoría.
- [ ] Editar una sintaxis conserva operadores desconocidos.
- [ ] Crear una sintaxis consulta `similar` y muestra el modal si hay
      coincidencias >= 70 %.
- [ ] Un `400` con `existing_id` se muestra y permite editar el existente.
- [ ] Eliminar maneja `204`, `200` y `400`.
- [ ] Si el backend pide `delete_explanation`, el frontend lo solicita.
- [ ] El selector de Platform usa un ID entero o `null`, sin default `1`.
- [ ] Si no hay sintaxis, el formulario muestra estado vacío y no inventa datos.
- [ ] Al publicar sin sintaxis, se muestra el error de `valid_sintaxis`.
- [ ] La vista de detalle muestra "Sin sintaxis" cuando es `null`.

### Imágenes

- [ ] El formulario de Platform permite seleccionar un archivo.
- [ ] El formulario de Journal permite seleccionar un archivo.
- [ ] La subida usa `multipart/form-data` con el campo `image`.
- [ ] La subida no usa `apiClient.post` con JSON.
- [ ] No se envía `Content-Type` manualmente en el `fetch` de `FormData`.
- [ ] Se muestra preview antes y después de subir.
- [ ] La respuesta actualiza `url_image` desde la ficha devuelta.
- [ ] Quitar imagen usa `DELETE /image/`, no `PATCH { url_image: null }`.
- [ ] Se manejan `400`, `404`, `401`, `403`, `415` y `503`.
- [ ] La imagen no se exige para publicar Platform ni Journal.

---

## 9. Ejemplos rápidos

### 9.1. Crear una sintaxis

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

### 9.2. Buscar sintaxis similares

```bash
curl -X POST http://localhost:8000/api/platforms/valid-sintaxis/similar/ \
  -H "Content-Type: application/json" \
  -d '{
    "booleans": ["AND", "OR"],
    "parenthesis": true,
    "fields": {"title": "ti"}
  }'
```

### 9.3. Asignar sintaxis a una plataforma

```bash
curl -X PATCH http://localhost:8000/api/platforms/10/ \
  -H "Content-Type: application/json" \
  -d '{"valid_sintaxis": 3}'
```

### 9.4. Subir imagen de plataforma

```bash
curl -X POST http://localhost:8000/api/platforms/10/image/ \
  -H "Cookie: sessionid=..." \
  -H "X-CSRFToken: ..." \
  -F "image=@logo.png"
```

### 9.5. Quitar imagen de plataforma

```bash
curl -X DELETE http://localhost:8000/api/platforms/10/image/ \
  -H "Cookie: sessionid=..." \
  -H "X-CSRFToken: ..."
```

### 9.6. Subir imagen de revista

```bash
curl -X POST http://localhost:8000/api/journals/7/image/ \
  -H "Cookie: sessionid=..." \
  -H "X-CSRFToken: ..." \
  -F "image=@portada.webp"
```

---

## 10. Preguntas frecuentes

**¿`ValidSintaxis` es un módulo aparte?**
No. Se administra desde el panel de edición de Platform. El selector de
sintaxis ofrece "Crear nueva" y "Editar", que abren un modal con el formulario
de checkboxes. No debe haber una entrada "Sintaxis válidas" en el menú ni una
página independiente como flujo principal.

**¿Por qué `valid_sintaxis` no es un checkbox en Platform?**
Porque una plataforma tiene una sola sintaxis. Es una FK única. El control
correcto es un select o radios. Los checkboxes son para los componentes
internos de `ValidSintaxis` (`booleans` y `fields`).

**¿Puedo enviar `booleans` como `"AND,OR"`?**
No. Debe ser `["AND", "OR"]`. Un string separado por comas no es el contrato y
puede ser rechazado o interpretado incorrectamente.

**¿Puedo enviar `parenthesis` como `"true"`?**
El serializer podría coercionarlo, pero el contrato es booleano. Usa
`true`/`false` desde un checkbox.

**¿`fields` puede tener claves vacías?**
Sí, el backend acepta `""`, pero es mejor omitir las claves no habilitadas.
La similitud ignora los valores vacíos.

**¿Puedo usar `url_image` en el POST de creación?**
Sí, para una URL externa. Para subir un archivo, primero crea la ficha y luego
usa `POST /image/`.

**¿Puedo borrar la imagen con `PATCH { "url_image": null }`?**
Puedes desasociarla, pero no se elimina el archivo de RustFS. Usa
`DELETE /image/`.

**¿La imagen es obligatoria?**
No. Ni Platform ni Journal la exigen para publicar.

**¿Journal tiene `valid_sintaxis`?**
No. Solo Platform.

**¿Qué pasa si el backend devuelve `valid_sintaxis` como objeto?**
Es la respuesta pública. Para mostrar, usa `.name`. Para editar, usa el
endpoint administrativo, que devuelve el ID entero.

**¿Qué pasa si el catálogo de sintaxis falla?**
Muestra un estado de error o vacío. No uses IDs de ejemplo. Un ID inventado
puede hacer fallar la creación o asociar una sintaxis incorrecta.
