# Contrato de respuesta final

Devuelve exclusivamente un objeto JSON con estas cinco claves:

- `estado`: `ok`, `fuera_de_tema`, `informacion_insuficiente` o `error_sistema`.
- `mensaje`: `null` para `ok`; texto breve en el idioma original para los demás estados.
- `programas_seleccionados`: lista de `{id,nombre,puntuacion,razon}`.
- `busquedas`: lista de `{plataforma_id,plataforma,cadena,justificacion}`.
- `filtros_no_aplicados`: lista de `{plataforma_id,plataforma,filtro}`.

La búsqueda genérica usa `plataforma_id: null` y `plataforma: "generica"`.

La `razon` debe citar la conclusión y su evidencia: mención explícita, áreas
coincidentes y relación temática. La `justificacion` debe citar cantidad de
revistas relacionadas, programas cubiertos, capacidades útiles y limitaciones.
Nunca narres razonamiento interno ni pasos de ejecución.

```json
{
  "estado": "ok",
  "mensaje": null,
  "programas_seleccionados": [
    {
      "id": 12,
      "nombre": "Ingeniería de Sistemas",
      "puntuacion": 0.79,
      "razon": "Fue mencionado y coincide con Inteligencia Artificial y Bases de Datos."
    }
  ],
  "busquedas": [
    {
      "plataforma_id": 3,
      "plataforma": "SciELO",
      "cadena": "ti((inteligencia artificial OR IA) AND educacion) AND py(2020-2025)",
      "justificacion": "Reúne 120 revistas vinculadas al programa y admite AND, OR, título y año mediante plantillas registradas."
    }
  ],
  "filtros_no_aplicados": [
    {"plataforma_id": 3, "plataforma": "SciELO", "filtro": "Idioma"}
  ]
}
```
