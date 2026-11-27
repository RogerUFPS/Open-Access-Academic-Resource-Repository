---
name: reglas-de-respuesta
description: Recomienda programas académicos y plataformas y genera cadenas de búsqueda verificables para consultas de literatura. Úsala para artículos, revistas, documentos académicos, plataformas o sintaxis de búsqueda; también clasifica solicitudes fuera de tema o con datos insuficientes.
---

# Objetivo

Convertir una consulta de investigación en programas académicos recomendados y,
cuando los datos lo permiten, una cadena de búsqueda válida por plataforma.

Flujo: consulta → intención → facetas y áreas pertinentes → programas →
cobertura de revistas y plataformas → términos → cadenas.

# Antes de responder

## Ejecución del servicio

El runtime ejecuta obligatoriamente las herramientas, valida sus contratos y
construye la respuesta final. El modelo recibe la sección de intención de esta
skill y el prompt de clasificación; devuelve una intención estructurada mediante
`classify_intent`, no decide qué scripts omitir ni redacta el JSON público.
`AGENT_CLASSIFICATION_MODE=stable` conserva el verificador anterior. El modo
`facets` es experimental y no superó la evaluación con los modelos actuales;
no debe activarse por defecto. En ese modo la pertinencia sin programa explícito
se revisa por facetas, sin recibir programas ni conteos de revistas.
El resto de selección y construcción se valida y ejecuta en el servidor.

1. Los contratos de herramientas están implementados en [scripts](./scripts/)
   y su adaptador permitido [tool_runner.py](./src/biblioteca_agent/tool_runner.py).
2. El contrato público de respuesta se valida en
   [contracts.py](./src/biblioteca_agent/contracts.py).

# Invariantes

1. Ejecuta scripts únicamente mediante la herramienta Python, enviando
   `script_name` y `script_args`; usa `{}` cuando no haya argumentos.
2. Usa ids, nombres, relaciones y capacidades exactamente como los devuelven
   las herramientas. No completes información ausente.
3. Los filtros usan su id convertido a clave JSON, por ejemplo
   `{"1":["es","en"],"3":"2020-2025"}`.
4. Si una herramienta devuelve un error o contrato inválido, corrige los
   argumentos y reintenta una vez. Si vuelve a fallar, devuelve `error_sistema`.
5. Una lista vacía de herramienta es válida. En la respuesta final,
   `estado=ok` requiere al menos un programa y una búsqueda. `null` significa
   desconocido, no `false`.
6. El RAG orienta intención y similitud; nunca crea ids, relaciones, filtros o
   capacidades del catálogo.
7. Responde exclusivamente con el JSON final requerido.

# Proceso

## 1. Intención y datos base

1. Conserva el prompt original y detecta su idioma ISO 639-1.
2. Conserva el idioma original del tema, nombres, siglas, cifras y fechas;
   traduce únicamente cuando el usuario lo solicite.
3. Normaliza el prompt y consulta `rag_search` una sola vez.
4. Obtén en paralelo programas, áreas y filtros.
5. Clasifica como `buscar_literatura`, `consultar_catalogo` o `fuera_de_tema`.
   Una consulta de cantidades o cobertura usa los nombres y conteos de
   herramientas y devuelve `informacion_catalogo`, sin una cadena artificial.
6. Identifica programas y áreas explícitas, implícitas o ambiguas solo con ids
   existentes en el catálogo.
7. Valida únicamente filtros pedidos explícitamente en el prompt actual. Las
   listas usan valores permitidos y los años `AAAA-AAAA` o límites explícitos
   `>=AAAA`, `<=AAAA`, `>AAAA`, `<AAAA`, `=AAAA`. El idioma detectado
   sirve para interpretar el texto, pero no se convierte en filtro por defecto.
8. Conserva poblaciones y disciplinas investigadas en el tema y en hasta cuatro
   conceptos. «Personal de enfermería» no es un programa destinatario.
   Los códigos ISO ambiguos solo indican idioma con una etiqueta explícita.
9. Los años y tipos de artículos se representan solo si la sintaxis lo permite;
   de lo contrario se registran como no aplicados. No se comparan
   con el año de origen ni con el tipo documental de la revista. «Reciente» sin
   años no autoriza inventar un periodo ni impide recomendar plataformas.
10. Conserva nombres originales. Solo retira de la etiqueta de comparación un
    prefijo numérico reconocible de clasificación (tres cifras y decimales
    opcionales); los nombres sin código y otros números permanecen intactos.
11. Fundamenta áreas inferidas con fragmentos literales en `evidencias_areas`.
    Recupera coincidencias léxicas de etiquetas si el modelo omite áreas. Si no
    hay evidencia ni coincidencias, permite una revisión dirigida adicional.
12. Excluye frases de petición del tema y programas que solo son destinatarios.
    No confundas estos últimos con poblaciones o disciplinas investigadas.
    Si interpretaciones incompatibles impiden elegir una disciplina, devuelve
    una pregunta específica en `aclaracion`, sin inventar áreas.
13. Decide `operacion`: nueva consulta, refinamiento o actualización de filtros.
    No heredes programas ni filtros en una pregunta autónoma, aunque comience
    con un marcador temporal. Quitar filtros conserva el tema previo. El
    servidor conserva un estado canónico, no instrucciones acumuladas del historial.
14. Usa `interpretaciones` cuando existan sentidos incompatibles sin contexto.
    No mantengas excepciones por términos. Una evidencia literal no basta para
    validar semánticamente un área: la revisión usa una salida estructurada
    separada, no una autocertificación de confianza. No supone un juez externo.
15. Solo en el modo experimental `facets`, cada faceta conserva un fragmento literal del tema e identifica áreas
    existentes y relación directa, parcial o sin correspondencia. No ocultes
    aspectos sin correspondencia ni fuerces una disciplina para llenar opciones.
    Las glosas de [alcance académico](./resources/catalog/academic_scopes.json)
    orientan el significado de las etiquetas; son editoriales, no definiciones
    oficiales, artículos ni relaciones nuevas. Una familia general no acredita
    especialidades de cualquier programa relacionado.
    En esa revisión, el modelo elige etiquetas exactas de un enum, no ids
    numéricos anónimos. El servidor convierte las etiquetas a ids existentes.
    Un resultado sin áreas, aunque diga «directa», se trata conservadoramente
    como ausencia de respaldo, no como recomendación ni error de entrada.

Si la consulta está fuera de tema, responde `fuera_de_tema` y termina.

## 2. Selección de programas

1. Con programa explícito, une áreas del tema con las de los programas indicados.
   En modo `facets`, sin programa explícito utiliza solo áreas aceptadas en la revisión por
   facetas. Las coincidencias léxicas rechazadas no vuelven a introducirse.
   Deriva los programas de las relaciones existentes del catálogo; el modelo
   no escoge programas. Evalúa disponibilidad de revistas después, nunca antes
   de la pertinencia. Conserva y explica programas pertinentes sin cobertura.
2. Pesa con 1.0 las áreas explícitas, implícitas o provenientes de programa, y
   con 0.5 las ambiguas. Multiplica por la especificidad del grafo: inversa de
   la raíz cuadrada del número de programas que comparten el área.
3. Consulta programas por áreas e incluye los programas explícitos.
4. Calcula:

   `puntuacion = 0.45 * explicito + 0.35 * cobertura_areas + 0.20 * similitud_tema`

5. `cobertura_areas` es la suma de pesos coincidentes dividida por la suma de
   todos los pesos. Redondea a cuatro decimales.
6. Desempata por cantidad de áreas coincidentes y luego por menor id. Conserva
   tres con revistas disponibles para los filtros aplicables al catálogo.
   En el modo experimental, prioriza cubrir pares faceta/área diferentes
   y no repetir el mismo respaldo. Esto evita perder una disciplina secundaria
   solo por su menor puntuación. No rellena puestos sin evidencia nueva.
    No completes puestos sin evidencia: un programa secundario requiere un área
   no genérica y cobertura ponderada >= 0.65 o coincidencia léxica específica.
   Es genérica un área compartida por al menos max(3, ceil(programas * 0.05)).
   Una inferencia confirmada por revisión independiente puede conservar un
   programa aunque su área sea compartida; especificidad no equivale a pertinencia.
   Con programa explícito, descarta inferencias ajenas a sus relaciones salvo
   evidencia léxica independiente del tema. Sin programa explícito y con
   recuperación léxica de varios aspectos, exige coincidencia del nombre del programa o
   dos áreas específicas verificadas; no conviertas cualquier disciplina que
   comparta matemáticas en una recomendación pedagógica.
   Una consulta genuinamente general, sin programa explícito y cuyas áreas son
   todas genéricas, puede recibir cobertura exploratoria, señalando ese alcance.

Para `similitud_tema`, usa la mayor proporción de términos significativos de una
etiqueta de área coincidente presentes en el tema; no compares códigos. Se acepta
evidencia léxica con al menos 65 % de los términos significativos de la etiqueta.
Los ejemplos RAG no contienen
relaciones ni ids de programas y por tanto no prueban esa relación.

## 3. Selección de plataformas

1. Consulta plataformas relacionadas con programas y filtros.
2. Obtén su sintaxis y descarta plataformas no configuradas.
3. Calcula cobertura de revistas distintas, sin sumar duplicados entre programas:

   `revistas = log(1 + total) / log(1 + max_total)`

   Si `max_total` es cero, usa cero.
4. Calcula `sintaxis` solo con capacidades modeladas y necesarias: operadores,
   paréntesis y plantillas explícitas. No penalices capacidades `null`.
   Es la proporción de filtros solicitados representables; sin filtros vale 1,
   porque una cadena temática simple no requiere operadores ni campos.
5. Calcula `puntuacion = 0.6 * sintaxis + 0.4 * revistas`, desempata por mayor
   total de revistas y conserva tres.

## 4. Términos y cadenas

1. Obtén títulos unificados y ejecuta YAKE una vez por plataforma.
2. Conserva todos los términos temáticos. Los conceptos deben proceder del tema;
   si omiten modificadores, recupéralos de los fragmentos adyacentes del tema.
   Si no pueden localizarse sin perder palabras o añaden otras, usa el tema completo.
3. Usa máximo cuatro grupos, sin inventar variantes. YAKE prioriza los grupos
   con evidencia del prompt, nunca introduce términos de títulos ajenos.
   Retira destinatarios que no pertenecen al tema y conceptos ya contenidos en
   otros antes de validar los grupos; no descartes grupos útiles por ese ruido.
4. Usa `AND` entre conceptos solo si está soportado. Las alternativas de filtros
   requieren `OR` y paréntesis explícitamente disponibles.
5. Usa comillas solo si `frase_exacta` es `true`.
6. Aplica campos y filtros únicamente mediante una plantilla no nula,
   reemplazando `{}` una vez. Idioma usa `language`. La plantilla `year` no
   define por sí sola operadores temporales: hasta modelarlos explícitamente,
   registra fechas como no aplicadas y no fabriques rangos dentro del campo.
7. Registra filtros imposibles de representar en `filtros_no_aplicados`.
8. Valida operadores, paréntesis, plantillas, términos vacíos y ausencia de
   capacidades supuestas.
9. No concatenes parámetros HTTP (`filter=`, `search=`) como expresiones booleanas
   de un buscador. Sin un adaptador de API, informa el filtro como no representable.
10. Justifica con cobertura disciplinar comprobada; no afirmes que el catálogo
    prueba la existencia de artículos específicos ni su efectividad clínica.

# Información insuficiente

Si faltan áreas o plataformas, ejecuta YAKE solo con el prompt y genera una
cadena genérica conservadora, sin campos ni filtros. Devuelve
`informacion_insuficiente` y explica qué dato del catálogo faltó.
Conserva los programas identificados aunque no tengan revistas. Distingue falta
de cobertura, restricciones sin resultados y ambigüedad que requiere aclaración.
