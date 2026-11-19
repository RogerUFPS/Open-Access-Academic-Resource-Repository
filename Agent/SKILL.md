---
name: reglas-de-respuesta
description: Recomienda programas académicos y plataformas y genera cadenas de búsqueda verificables para consultas de literatura. Úsala para artículos, revistas, documentos académicos, plataformas o sintaxis de búsqueda; también clasifica solicitudes fuera de tema o con datos insuficientes.
---

# Objetivo

Convertir una consulta de investigación en programas académicos recomendados y,
cuando los datos lo permiten, una cadena de búsqueda válida por plataforma.

Flujo: consulta → intención → programas → plataformas → términos → cadenas.

# Antes de responder

1. Lee [los contratos de herramientas](./references/tool-contracts.md) antes de
   invocar scripts o interpretar sus resultados.
2. Lee [el contrato de respuesta](./references/response-contract.md) antes de
   construir el JSON final.

# Invariantes

1. Ejecuta scripts únicamente mediante la herramienta Python, enviando
   `script_name` y `script_args`; usa `{}` cuando no haya argumentos.
2. Usa ids, nombres, relaciones y capacidades exactamente como los devuelven
   las herramientas. No completes información ausente.
3. Los filtros usan su id convertido a clave JSON, por ejemplo
   `{"1":["es","en"],"3":"2020-2025"}`.
4. Si una herramienta devuelve un error o contrato inválido, corrige los
   argumentos y reintenta una vez. Si vuelve a fallar, devuelve `error_sistema`.
5. Una lista vacía es válida. `null` significa desconocido, no `false`.
6. El RAG orienta intención y similitud; nunca crea ids, relaciones, filtros o
   capacidades del catálogo.
7. Responde exclusivamente con el JSON final requerido.

# Proceso

## 1. Intención y datos base

1. Conserva el prompt original y detecta su idioma ISO 639-1.
2. Tradúcelo al español si hace falta, conservando nombres, siglas, cifras y fechas.
3. Normaliza el prompt y consulta `rag_search` una sola vez.
4. Obtén en paralelo programas, áreas y filtros.
5. Clasifica como `buscar_literatura` o `fuera_de_tema`.
6. Identifica programas y áreas explícitas, implícitas o ambiguas solo con ids
   existentes en el catálogo.
7. Valida filtros. Las listas usan valores permitidos y los años `AAAA-AAAA`.
   Si no se menciona idioma, usa el detectado solo si el catálogo lo permite.

Si la consulta está fuera de tema, responde `fuera_de_tema` y termina.

## 2. Selección de programas

1. Une áreas explícitas, implícitas y ambiguas con las áreas de programas
   mencionados explícitamente.
2. Pesa con 1.0 las áreas explícitas, implícitas o provenientes de programa, y
   con 0.5 las ambiguas.
3. Consulta programas por áreas e incluye los programas explícitos.
4. Calcula:

   `puntuacion = 0.45 * explicito + 0.35 * cobertura_areas + 0.20 * similitud_tema`

5. `cobertura_areas` es la suma de pesos coincidentes dividida por la suma de
   todos los pesos. Redondea a cuatro decimales.
6. Desempata por cantidad de áreas coincidentes y luego por menor id. Conserva tres.

Para `similitud_tema`, usa 1 si un ejemplo RAG vincula directamente tema y
programa, 0.5 si la relación es parcial y 0 sin evidencia. Sin ejemplos, usa
coincidencias normalizadas del tema, programa y áreas.

## 3. Selección de plataformas

1. Consulta plataformas relacionadas con programas y filtros.
2. Obtén su sintaxis y descarta plataformas no configuradas.
3. Calcula cobertura de revistas:

   `revistas = log(1 + total) / log(1 + max_total)`

   Si `max_total` es cero, usa cero.
4. Calcula `sintaxis` solo con capacidades modeladas y necesarias: operadores,
   paréntesis y plantillas explícitas. No penalices capacidades `null`.
5. Calcula `puntuacion = 0.6 * sintaxis + 0.4 * revistas`, desempata por mayor
   total de revistas y conserva tres.

## 4. Términos y cadenas

1. Obtén títulos unificados y ejecuta YAKE una vez por plataforma.
2. Parte de términos cuyo origen sea `prompt`. Un término de plataforma solo
   puede enriquecer un grupo compatible.
3. Usa máximo cuatro grupos y seis variantes por grupo.
4. Usa `OR` entre variantes solo si está soportado y paréntesis cuando sean
   necesarios. Usa `AND` entre conceptos solo si está soportado.
5. Usa comillas solo si `frase_exacta` es `true`.
6. Aplica campos y filtros únicamente mediante una plantilla no nula,
   reemplazando `{}` una vez. Idioma usa `language` y fecha usa `year`.
7. Registra filtros imposibles de representar en `filtros_no_aplicados`.
8. Valida operadores, paréntesis, plantillas, términos vacíos y ausencia de
   capacidades supuestas.

# Información insuficiente

Si faltan áreas o plataformas, ejecuta YAKE solo con el prompt y genera una
cadena genérica conservadora, sin campos ni filtros. Devuelve
`informacion_insuficiente` y explica qué dato del catálogo faltó.
