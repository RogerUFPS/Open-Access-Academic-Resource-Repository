# Contratos de herramientas

Todas las herramientas reciben un objeto JSON y devuelven un objeto JSON. Los
ids siempre provienen del snapshot activo; una lista vacía es válida.

## Catálogos

- `scripts/normalize_text.py`
  - Entrada: `{"texto":"Inteligencia Artificial en la Educación"}`
  - Salida: `{"prompt_normalizado":"inteligencia artificial en la educacion"}`
- `scripts/get_academic_programs.py`
  - Entrada: `{}`
  - Salida: `{"programas":[{"id":12,"nombre":"Ingeniería de Sistemas","nombre_normalizado":"ingenieria de sistemas"}]}`
- `scripts/get_knowledge_areas.py`
  - Entrada: `{}`
  - Salida: `{"areas":[{"id":7,"nombre":"Inteligencia Artificial","nombre_normalizado":"inteligencia artificial"}]}`
- `scripts/get_valid_filters.py`
  - Entrada: `{}`
  - Devuelve `filtros` con `id`, `clave`, `nombre`, `tipo`, `valores_validos` y `formato`.
  - Usa el `id` convertido a texto como clave de filtros. `clave` solo describe su semántica.

## Relaciones

- `scripts/get_areas_from_program.py`
  - Entrada: `{"programas":[12,31]}`
  - Devuelve cada `programa_id` con su lista de `{area_id,nombre}`.
- `scripts/get_programs_from_areas.py`
  - Entrada: `{"areas":[7,9]}`
  - Devuelve `programa_id`, `nombre`, `areas_coincidentes` y `cantidad_areas_coincidentes`.
- `scripts/get_platforms_related_to_programs.py`
  - Entrada: `{"programas":[12,31],"filtros":{"1":["es","en"],"3":"2020-2025"}}`
  - Devuelve plataformas y, por programa, `cantidad_revistas` después de aplicar filtros.
- `scripts/get_platform_journal_title_unified.py`
  - Recibe `plataformas`, `programas` y `filtros`.
  - Devuelve `textos_unificados` con `plataforma_id` y `texto`.

## Sintaxis válida

`scripts/get_valid_sintaxis.py` recibe `{"plataformas":[3]}`. Para cada
plataforma devuelve:

```json
{
  "plataforma_id": 3,
  "configurada": true,
  "operadores": {"AND": true, "OR": true, "NOT": true},
  "parentesis": true,
  "campos": {
    "title": {"identificador": "ti({})", "plantilla": "ti({})"},
    "author": {"identificador": null, "plantilla": null},
    "subject": {"identificador": "su", "plantilla": null},
    "issn": {"identificador": null, "plantilla": null},
    "language": {"identificador": "la({})", "plantilla": "la({})"},
    "year": {"identificador": "py({})", "plantilla": "py({})"}
  },
  "frase_exacta": null,
  "truncamiento": null,
  "caracteres_escape": null,
  "max_longitud": null,
  "idiomas": ["es", "en", "pt"],
  "idioma_principal": "es",
  "capacidades_no_modeladas": [
    "frase_exacta", "truncamiento", "caracteres_escape", "max_longitud"
  ]
}
```

Reglas obligatorias:

- `booleans` se normaliza en `operadores` y `parenthesis` en `parentesis`.
- Los campos canónicos son `title`, `author`, `subject`, `issn`, `language` y `year`.
- `identificador` conserva literalmente el dato registrado.
- `plantilla` solo es utilizable cuando contiene `{}`. Nunca inventes una gramática.
- `null` significa desconocido o no modelado, no `false`.
- Si `configurada` es `false`, no generes sintaxis específica.

## YAKE

`scripts/yake_extract_keywords.py` recibe:

```json
{
  "prompt_normalizado": "inteligencia artificial en la educacion",
  "texto_unificado": "educacion tecnologia aprendizaje automatico",
  "idioma_texto": "es",
  "umbral_relevancia": 0.5,
  "excluir_genericas": true
}
```

Devuelve `palabras_clave` con `termino`, `relevancia` y `origen`. La relevancia
invierte la escala nativa de YAKE: 1 es mejor. El script usa stopwords de YAKE
y el catálogo local de términos genéricos.
