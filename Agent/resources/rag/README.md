# Ejemplos aprobados del RAG

Editar [approved_examples.json](approved_examples.json), un array JSON con un
objeto por ejemplo y campos en varias líneas. No es un archivo JSONL ni un
historial de usuarios.

Cada objeto tiene id único, prompt, respuesta (intención esperada) y notas.
Copiar un objeto existente, asignar un id nuevo y escribir una pregunta realista.
En respuesta, tipo admite buscar_literatura o fuera_de_tema; tema contiene el
tema esperado sin filtros. Los arrays de programas/áreas deben quedar vacíos:
sus IDs se resuelven contra el catálogo activo, nunca se memorizan aquí.
Los filtros solo describen lo explícito en ese prompt y no se heredan durante
una consulta; el servidor los extrae y valida nuevamente con el catálogo real.
Las claves de filtros del contrato son "1" (idioma), "2" (tipo de documento)
y "3" (rango de años); no confundirlas con IDs de programas o áreas.

Plantilla mínima de un nuevo objeto dentro del array (añadir la coma entre
objetos y no usar comentarios ni comas finales, porque es JSON estricto):

```json
{
  "id": "rag-013-ejemplo-nuevo",
  "prompt": "Busco literatura sobre redes neuronales",
  "respuesta": {
    "tipo": "buscar_literatura",
    "tema": "redes neuronales",
    "programas_explicitos": [],
    "areas_explicitas": [],
    "areas_implicitas": [],
    "areas_ambiguas": [],
    "filtros": {}
  },
  "notas": "Revisado: no se solicitaron filtros ni programa específico."
}
```

Al iniciar con AUTO_INDEX_RAG=true, el servicio valida el lote completo y
reemplaza el índice SQLite FTS5 en /tmp/biblioteca/rag.sqlite3. El índice es
reconstruible; este JSON versionado es la fuente persistente. Un lote inválido
se rechaza antes de reemplazar los datos. No se entrenan pesos ni se incorporan
automáticamente conversaciones.

Después de revisar cambios: ejecutar las pruebas Docker, reconstruir la imagen
y recrear la API local, o volver a desplegar el adaptador Modal. No hay endpoint
administrativo de edición/indexación implementado. No incluir datos personales.

Comprobación desde Agent:

```bash
docker compose --profile test run --build --rm --no-deps tests
```
