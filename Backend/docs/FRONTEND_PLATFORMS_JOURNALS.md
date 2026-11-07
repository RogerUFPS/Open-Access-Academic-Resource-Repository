# Frontend: Plataformas y Revistas

Guía de integración para el panel administrativo. Describe las reglas vigentes
del backend, los endpoints que debe consumir el frontend y una propuesta visual
para que los formularios sean claros y consistentes.

> Regla clave: el usuario **solo selecciona programas académicos**. Las áreas
> del conocimiento siempre las calcula el backend a partir de esos programas.
> Nunca envíes `knowledge_areas` en `POST`, `PUT` o `PATCH`.

---

## 1. Reglas de negocio

### 1.1. Plataformas (`Platform`)

| Regla | Comportamiento |
| --- | --- |
| `academic_programs` | Opcional. Se puede seleccionar manualmente. |
| `knowledge_areas` | Solo lectura. Se derivan de los programas efectivos. |
| Publicar sin programas | Permitido. |
| Publicar sin áreas | Permitido. |
| Programas derivados | También llegan desde las revistas elegibles asociadas. |
| Áreas derivadas | Unión de las áreas de todos los programas efectivos (manuales + derivados). |

Flujo de clasificación:

```text
AcademicProgram ↔ KnowledgeArea        catálogo, fuente de verdad
Journal ↔ AcademicProgram              programa de la revista
Journal ↔ Platform                     revista indexada en la plataforma
Platform ↔ AcademicProgram             manual (opcional) + derivado
Platform ↔ KnowledgeArea               derivado de los programas efectivos
```

### 1.2. Revistas (`Journal`)

| Regla | Comportamiento |
| --- | --- |
| `academic_programs` | Obligatorio para **publicar**. Puede guardarse como borrador sin él. |
| `knowledge_areas` | Solo lectura. Se derivan de los programas seleccionados. |
| Enviar `knowledge_areas` | Se ignora. No crea ni modifica relaciones. |
| Publicar sin programas | Rechazado con error en `academic_programs`. |

Flujo de clasificación:

```text
AcademicProgram → SharedAcademicProgramKnowledgeArea → KnowledgeArea
        ↓
Journal ↔ AcademicProgram
        ↓
Journal ↔ KnowledgeArea (derivada)
```

---

## 2. Endpoints que debe usar el frontend

### 2.1. Catálogo

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/api/catalog/academic-programs/` | Opciones del selector de programas. Admite `search`, `page`, `page_size`, `ordering`. |
| `GET` | `/api/catalog/academic-programs/{id}/knowledge-areas/` | Previsualizar las áreas de un programa. |
| `GET` | `/api/catalog/knowledge-areas/` | Consultar nombres/IDs de áreas para mostrar etiquetas. |
| `GET` | `/api/catalog/institutions/` | Selector de instituciones de la plataforma. |
| `GET` | `/api/catalog/languages/` | Selector de idiomas. |
| `GET` | `/api/catalog/countries/` | Selector de países. |
| `GET` | `/api/catalog/material-types/` | Selector de tipos de material. |
| `GET` | `/api/catalog/editorials/` | Selector de editorial de la revista. |

Los catálogos devuelven resultados paginados (`results`, `count`, `next`,
`previous`). Para selectores con búsqueda, usa `search` y `page_size` pequeño.

### 2.2. Plataformas

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/api/platforms/` | Listado administrativo. |
| `POST` | `/api/platforms/` | Crear plataforma. |
| `GET` | `/api/platforms/{id}/` | Detalle. |
| `PATCH` | `/api/platforms/{id}/` | Actualización parcial. |
| `POST` | `/api/platforms/{id}/publish/` | Publicar. |
| `POST` | `/api/platforms/{id}/mark-obsolete/` | Marcar obsoleta. |
| `POST` | `/api/platforms/{id}/reactivate/` | Reactivar a borrador. |
| `POST` | `/api/platforms/{id}/restore/` | Restaurar eliminada. |
| `POST` | `/api/platforms/{id}/check-link/` | Registrar/verificar URL pública. |
| `POST` | `/api/platforms/{id}/image/` | Subir imagen (`multipart/form-data`, campo `image`). |
| `DELETE` | `/api/platforms/{id}/image/` | Quitar imagen. |
| `GET` | `/api/platforms/valid-sintaxis/` | Opciones de sintaxis de búsqueda. |
| `GET` | `/api/platforms/public/` | Consulta pública de publicadas. |

Crear una plataforma:

```http
POST /api/platforms/
Content-Type: application/json
```

```json
{
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
  "academic_programs": [1, 4]
}
```

`academic_programs` puede omitirse o enviarse como `[]`. No envíes
`knowledge_areas`.

Respuesta resumida:

```json
{
  "id": 10,
  "name": "Repositorio institucional",
  "status": "borrador",
  "academic_programs": [
    {
      "id": 1,
      "name": "Ingeniería de Sistemas",
      "is_manual": true,
      "is_derived": false,
      "editable": true
    }
  ],
  "knowledge_areas": [
    {
      "id": 3,
      "name": "Ingeniería",
      "is_manual": false,
      "is_derived": true,
      "editable": false
    }
  ]
}
```

Errores de publicación habituales:

```json
{
  "url": "La URL pública debe verificarse antes de publicar la plataforma.",
  "valid_sintaxis": "La plataforma debe tener una sintaxis de búsqueda asociada.",
  "institutions": "La plataforma debe tener al menos una institución responsable activa asociada.",
  "countries": "La plataforma debe tener al menos un país activo asociado.",
  "material_types": "La plataforma debe tener al menos un tipo de material activo asociado.",
  "languages": "La plataforma debe tener al menos un idioma activo asociado."
}
```

No aparecerán errores de `academic_programs` ni `knowledge_areas`.

### 2.3. Revistas

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/api/journals/` | Listado administrativo. |
| `POST` | `/api/journals/` | Crear revista. |
| `GET` | `/api/journals/{id}/` | Detalle. |
| `PATCH` | `/api/journals/{id}/` | Actualización parcial. |
| `POST` | `/api/journals/{id}/publish/` | Validar y publicar. |
| `POST` | `/api/journals/{id}/deactivate/` | Desactivar. |
| `POST` | `/api/journals/{id}/restore/` | Restaurar eliminada. |
| `POST` | `/api/journals/{id}/image/` | Subir imagen (`multipart/form-data`). |
| `DELETE` | `/api/journals/{id}/image/` | Quitar imagen. |
| `GET` | `/api/journals/{id}/platforms/` | Asociaciones vigentes con plataformas. |
| `GET` | `/api/journals/public/` | Consulta pública de activas y validadas. |

Crear una revista:

```json
{
  "issn": "1476-4687",
  "title": "Nature",
  "editorial": 1,
  "publication_date": "1869-11-04",
  "has_apc": false,
  "languages": [1],
  "countries": [1],
  "material_types": [1],
  "academic_programs": [1],
  "platforms": [
    {
      "platform": 1,
      "journal_url": "https://example.org/nature",
      "has_full_text": true
    }
  ]
}
```

No envíes `knowledge_areas`. La respuesta incluye las áreas derivadas:

```json
{
  "id": 7,
  "issn": "1476-4687",
  "title": "Nature",
  "academic_programs": [1],
  "knowledge_areas": [
    {
      "id": 3,
      "name": "Ciencias naturales",
      "is_manual": false,
      "is_derived": true,
      "editable": false
    }
  ]
}
```

Errores de publicación habituales:

```json
{
  "academic_programs": "La revista debe tener al menos un valor vigente.",
  "platforms": "La revista no tiene plataformas asociadas.",
  "licenses": "La revista debe tener al menos una licencia vigente.",
  "editorial": "La revista debe tener una editorial vigente.",
  "publication_date": "La fecha de publicación es obligatoria."
}
```

---

## 3. Implementación recomendada en el frontend

### 3.1. Estado de los formularios

Plataforma:

```js
const platformForm = {
  name: "",
  public_url: "",
  is_harvestable: false,
  base_api_url: "",
  api_key: "",
  url_image: "",
  requires_registration: false,
  has_access_text: false,
  valid_sintaxis: null,
  institutions: [],
  languages: [],
  countries: [],
  material_types: [],
  academic_programs: [], // opcional
};
```

Revista:

```js
const journalForm = {
  issn: "",
  title: "",
  editorial: null,
  publication_date: "",
  has_apc: false,
  url_image: "",
  languages: [],
  countries: [],
  material_types: [],
  academic_programs: [], // obligatorio para publicar
  platforms: [],
  licenses: [],
};
```

No incluyas `knowledge_areas` en el estado que se envía al backend. Si necesitas
mostrarlas antes de guardar, mantén un estado separado de solo lectura:

```js
const [derivedAreas, setDerivedAreas] = useState([]);
```

### 3.2. Selector de programas académicos

Comportamiento:

1. Cargar opciones con `GET /api/catalog/academic-programs/?search=...`.
2. Mostrar un multi-select con búsqueda y chips.
3. Al cambiar la selección, calcular una vista previa de áreas:

```js
async function previewAreas(programIds) {
  const responses = await Promise.all(
    programIds.map((id) =>
      api.get(`/catalog/academic-programs/${id}/knowledge-areas/?page_size=100`)
    )
  );

  const byId = new Map();
  responses.forEach((response) => {
    (response.data.results ?? response.data).forEach((area) => {
      byId.set(area.id, area);
    });
  });

  return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
}
```

4. Muestra las áreas como chips bloqueados con la etiqueta
   **“Derivada automáticamente”**.
5. Después de guardar, reemplaza la vista previa con el campo
   `knowledge_areas` que devuelve el backend.

En la plataforma el selector de programas debe ser **opcional**:

```text
Programas académicos (opcional)
[ Buscar programa... ]
[Ingeniería de Sistemas ×] [Ingeniería Civil ×]

Áreas del conocimiento (automáticas)
[Ingeniería 🔒] [Ciencias de la Computación 🔒]
```

En la revista debe ser **obligatorio para publicar**:

```text
Programas académicos *
[ Buscar programa... ]
[Ingeniería de Sistemas ×]

Áreas del conocimiento (automáticas)
[Ingeniería 🔒]
```

Marca el campo como obligatorio solo cuando el usuario intente publicar. Para
guardar un borrador se permite `academic_programs: []`.

### 3.3. Badges de procedencia

Usa los flags que devuelve el backend:

| `is_manual` | `is_derived` | Interpretación | UI sugerida |
| --- | --- | --- | --- |
| `true` | `false` | Selección manual | Chip normal, editable. |
| `false` | `true` | Derivada de programas/revistas | Chip con candado y texto “Automática”. |
| `true` | `true` | Manual y derivada a la vez | Chip con doble badge; no permitir quitar. |

En `knowledge_areas` de Platform y Journal siempre será `editable: false`.
No renderices un botón para eliminarlas.

### 3.4. Checklist de publicación de plataforma

Antes de habilitar el botón **Publicar**, valida:

- [ ] `public_url` registrada y verificada (`check-link` con `is_active=true`).
- [ ] `valid_sintaxis` seleccionada.
- [ ] Al menos una institución.
- [ ] Al menos un país.
- [ ] Al menos un idioma.
- [ ] Al menos un tipo de material.
- [ ] Si `is_harvestable=true`, `base_api_url` presente.
- [ ] Si hay `api_key`, `base_api_url` presente.

No incluyas programas académicos ni áreas en el checklist.

### 3.5. Checklist de publicación de revista

Antes de habilitar **Publicar**, valida:

- [ ] `issn` y `title`.
- [ ] `editorial`.
- [ ] `publication_date`.
- [ ] Al menos un idioma.
- [ ] Al menos un país.
- [ ] Al menos un tipo de material.
- [ ] **Al menos un programa académico.**
- [ ] Al menos una plataforma asociada y publicada.
- [ ] Al menos una licencia.

Las áreas del conocimiento no se validan por separado.

### 3.6. Manejo de errores

Mapea las claves del error a los campos del formulario:

```js
const FIELD_LABELS = {
  name: "Nombre",
  public_url: "URL pública",
  valid_sintaxis: "Sintaxis de búsqueda",
  institutions: "Instituciones",
  countries: "Países",
  languages: "Idiomas",
  material_types: "Tipos de material",
  academic_programs: "Programas académicos",
  platforms: "Plataformas",
  licenses: "Licencias",
  editorial: "Editorial",
  publication_date: "Fecha de publicación",
  url: "URL pública",
  detail: "Error",
};
```

Reglas:

- Muestra errores por campo junto al control.
- Muestra un resumen en la parte superior del formulario.
- Si el backend responde 400 al publicar, mantén el formulario abierto y
  resalta los campos faltantes.
- No muestres errores de `knowledge_areas`: el frontend no lo envía.

### 3.7. Caché y rendimiento

- Carga los catálogos una vez por sesión del formulario.
- Usa búsqueda con debounce (300–400 ms) para programas académicos.
- Cachea las áreas por programa para evitar repetir peticiones al abrir/cerrar
  chips.
- Después de guardar, usa la respuesta del `POST`/`PATCH` como fuente de verdad
  para `academic_programs` y `knowledge_areas`.

---

## 4. Propuesta visual

### 4.1. Estructura del formulario de plataforma

```text
┌─────────────────────────────────────────────────────────────┐
│ Nueva plataforma                              [Borrador]    │
├─────────────────────────────────────────────────────────────┤
│ 1. Información general                                      │
│    Nombre · URL pública · Imagen                            │
│                                                             │
│ 2. Cobertura y acceso                                       │
│    Fechas (solo lectura) · Registro · Texto completo        │
│                                                             │
│ 3. Cosecha                                                  │
│    Interruptor · base_api_url · api_key                     │
│                                                             │
│ 4. Clasificación del catálogo                               │
│    Instituciones · Idiomas · Países · Tipos de material     │
│                                                             │
│ 5. Clasificación académica (opcional)                       │
│    Programas académicos                                     │
│    Áreas del conocimiento (automáticas, bloqueadas)         │
│                                                             │
│ 6. Sintaxis de búsqueda                                     │
│    Selector de sintaxis                                     │
├─────────────────────────────────────────────────────────────┤
│ [Cancelar]                         [Guardar] [Publicar]     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2. Estructura del formulario de revista

```text
┌─────────────────────────────────────────────────────────────┐
│ Nueva revista                                 [Borrador]    │
├─────────────────────────────────────────────────────────────┤
│ 1. Identificación                                           │
│    ISSN · Título · Editorial · Fecha de publicación         │
│                                                             │
│ 2. Acceso y licencias                                       │
│    Imagen · APC · Licencias                                 │
│                                                             │
│ 3. Clasificación del catálogo                               │
│    Idiomas · Países · Tipos de material                     │
│                                                             │
│ 4. Clasificación académica                                  │
│    Programas académicos *                                   │
│    Áreas del conocimiento (automáticas, bloqueadas)         │
│                                                             │
│ 5. Plataformas                                              │
│    Plataforma · URL de la revista · Texto completo          │
├─────────────────────────────────────────────────────────────┤
│ [Cancelar]                         [Guardar] [Publicar]     │
└─────────────────────────────────────────────────────────────┘
```

### 4.3. Componentes sugeridos

- **`AcademicProgramSelect`**: multi-select con búsqueda, chips y contador.
- **`DerivedKnowledgeAreas`**: lista de chips bloqueados con candado,
  skeletons mientras carga y estado vacío:
  - Plataforma: “Sin áreas derivadas. Puedes publicar sin clasificación.”
  - Revista: “Selecciona programas académicos para ver las áreas.”
- **`PublishChecklist`**: panel lateral o modal con los requisitos y su estado.
- **`OriginBadge`**: badge `Manual` / `Automática`.
- **`FormSection`**: tarjeta con título, descripción y separación visual.
- **`FieldError`**: mensaje bajo el control, con `aria-describedby`.

### 4.4. Estados vacíos y de carga

| Caso | UI |
| --- | --- |
| Sin programas seleccionados (Platform) | “Clasificación académica opcional”. |
| Sin programas seleccionados (Journal) | “Selecciona al menos un programa para publicar”. |
| Sin áreas derivadas | “Aún no hay áreas asociadas”. |
| Cargando áreas | Skeleton de chips. |
| Error al previsualizar áreas | Chip de error y reintento. |
| Guardado exitoso | Toast “Cambios guardados”. |
| Error de publicación | Resumen + campos resaltados. |

### 4.5. Accesibilidad y responsive

- Usa `aria-disabled="true"` en chips de áreas automáticas.
- No dependas solo del color para indicar procedencia: usa texto e icono.
- En móvil, los selectores deben ocupar todo el ancho y las secciones deben
  apilarse verticalmente.
- Mantén el botón de publicar visible en un footer sticky.

---

## 5. Flujo de guardado y publicación

### 5.1. Plataforma

```text
1. Cargar catálogos.
2. Usuario completa la ficha.
3. Guardar:
   POST /api/platforms/  o  PATCH /api/platforms/{id}/
   body.academic_programs = IDs seleccionados (opcional)
   body.knowledge_areas = NO enviar
4. Tomar academic_programs y knowledge_areas de la respuesta.
5. Verificar URL:
   POST /api/platforms/{id}/check-link/
6. Publicar:
   POST /api/platforms/{id}/publish/
7. Si 400, mostrar errores y volver al formulario.
```

### 5.2. Revista

```text
1. Cargar catálogos y plataformas.
2. Usuario completa la ficha.
3. Guardar:
   POST /api/journals/  o  PATCH /api/journals/{id}/
   body.academic_programs = IDs seleccionados
   body.knowledge_areas = NO enviar
4. Tomar knowledge_areas derivadas de la respuesta.
5. Publicar:
   POST /api/journals/{id}/publish/
6. Si 400, resaltar academic_programs, plataformas, licencias, etc.
```

---

## 6. Resumen de contratos

### 6.1. Campos que el frontend envía

Plataforma:

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
academic_programs   ← opcional
```

Revista:

```text
issn
title
editorial
publication_date
url_image
has_apc
languages
countries
material_types
academic_programs   ← obligatorio para publicar
platforms
licenses
```

### 6.2. Campos que el frontend solo lee

```text
id
status
start_period
finish_period
validated_by
validated_at
knowledge_areas
created_by
created_at
updated_by
updated_at
deleted_by
deleted_at
delete_explanation
```

### 6.3. Regla de oro

```text
Programas académicos → el usuario los elige.
Áreas del conocimiento → el backend las deriva. Nunca se envían.
```

---

## 7. Checklist de pruebas del frontend

- [ ] Crear una plataforma sin `academic_programs` y publicarla correctamente.
- [ ] Crear una plataforma con programas y comprobar que las áreas aparecen
      como automáticas.
- [ ] Intentar enviar `knowledge_areas` y verificar que el backend lo ignora.
- [ ] Editar una plataforma y quitar un programa: las áreas deben recalcularse.
- [ ] Crear una revista sin programas y comprobar que el borrador se guarda.
- [ ] Intentar publicar una revista sin programas: debe fallar en
      `academic_programs`.
- [ ] Publicar una revista con programas y comprobar las áreas derivadas.
- [ ] Verificar que los badges `Manual`/`Automática` coinciden con la respuesta.
- [ ] Verificar el checklist de publicación en ambos formularios.
- [ ] Verificar estados de carga, vacío y error.
