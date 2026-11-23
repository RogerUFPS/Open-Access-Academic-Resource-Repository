# Indicadores administrativos

## Objetivo

El endpoint de indicadores reúne en una sola respuesta las métricas
administrativas utilizadas por el panel del directorio académico.

## Endpoint

```http
GET /api/indicators/
```

La ruta requiere una sesión autenticada y el permiso:

```text
indicators.indicators.view
```

Respuestas principales:

- `200 OK`: indicadores calculados correctamente.
- `401 Unauthorized`: no existe una sesión autenticada.
- `403 Forbidden`: el usuario no tiene el permiso requerido o no ha
  completado el MFA cuando este sea obligatorio.

## Reglas de cálculo

### Revistas consideradas

Las métricas de revistas parten de registros que cumplen:

```text
deleted_at IS NULL
```

Una revista se considera publicada cuando además cumple:

```text
active = true
validated_at IS NOT NULL
```

La fecha de publicación utilizada en las series temporales es `validated_at`.
Las fechas se calculan usando la zona horaria configurada por Django.

### Revistas publicadas

`published_journals` es el total de revistas no eliminadas que están activas y
han sido validadas.

### Publicadas durante el mes actual

`published_journals_this_month` cuenta las revistas publicadas desde el primer
día del mes actual hasta el primer día del mes siguiente, usando
`validated_at`.

### Revistas pendientes

`pending_journals` cuenta las revistas no eliminadas que cumplen al menos una
de estas condiciones:

```text
active = false
OR
validated_at IS NULL
```

### Publicaciones por mes

`publications_by_month` contiene una serie de 12 elementos, ordenada desde el
mes más antiguo hasta el mes actual. Cada elemento tiene:

- `month`: mes en formato `YYYY-MM`.
- `count`: cantidad de revistas publicadas durante ese mes.

Solo se incluyen revistas que cumplen la definición de revista publicada.

### Disponibilidad de enlaces

`link_availability` se calcula sobre los registros devueltos por
`current_link_logs()`, que representa el último estado vigente de cada enlace.

- `total`: cantidad total de enlaces con estado vigente.
- `available`: enlaces cuyo último chequeo existe y están activos.
- `percentage`: porcentaje de enlaces disponibles, redondeado a dos decimales.

Cuando no existen enlaces vigentes, `percentage` y `available` son `0` y
`total` también es `0`.

### Revistas por área de conocimiento

`journals_by_knowledge_area` agrupa revistas por áreas de conocimiento.
Solo se consideran relaciones y registros vigentes:

- La relación revista-área no está eliminada.
- El área no está eliminada.
- La revista no está eliminada, está activa y está validada.

Cada elemento contiene:

- `id`: identificador del área.
- `name`: nombre del área.
- `journals`: cantidad de revistas distintas asociadas.

## Respuesta

Ejemplo de respuesta exitosa:

```json
{
  "published_journals": 24,
  "published_journals_this_month": 3,
  "pending_journals": 8,
  "link_availability": {
    "percentage": 92.86,
    "available": 39,
    "total": 42
  },
  "publications_by_month": [
    {
      "month": "2025-12",
      "count": 1
    },
    {
      "month": "2026-01",
      "count": 0
    }
  ],
  "journals_by_knowledge_area": [
    {
      "id": 4,
      "name": "Ciencias de datos",
      "journals": 6
    }
  ]
}
```

La respuesta real siempre contiene 12 elementos en `publications_by_month`;
el ejemplo se acorta únicamente para facilitar la lectura.

## Implementación y pruebas

La implementación se encuentra en:

```text
Backend/apps/indicators/views.py
Backend/apps/indicators/urls.py
```

Las pruebas del contrato y del permiso están en:

```text
Backend/apps/indicators/tests/test_api.py
```

La documentación OpenAPI del endpoint también se declara mediante
`extend_schema` en `views.py`.
