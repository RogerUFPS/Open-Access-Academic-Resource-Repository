# Implementación y decisiones de diseño

## Resultado

El directorio contiene un único servicio desplegable en RunPod. Se eliminaron
Compose, vLLM local, pesos, cachés de Hugging Face y configuración CUDA. La
imagen del agente solo necesita CPU y consume inferencia remota.

## Capas

1. **API:** FastAPI autentica, valida y aplica contrapresión por réplica.
2. **Registro de modelos:** `config/models.json` define alias, checkpoint,
   nombre servido y opciones no secretas de Qwen, GLM y Llama.
3. **Adaptador de inferencia:** un cliente `AsyncOpenAI` reutilizable por modelo
   resuelve URL y clave desde secretos y habla con vLLM.
4. **Orquestación:** el tool loop limita rondas y tokens y preserva
   `tool_call_id` según el contrato OpenAI.
5. **Herramientas:** scripts Python en allowlist reciben y emiten JSON, tienen
   timeout y nunca usan `shell=True`.
6. **Datos:** el catálogo llega por snapshot HTTPS o por el fixture incluido;
   no hay conexión a Django ni PostgreSQL.
7. **RAG:** SQLite FTS5 se construye con ejemplos aprobados durante el arranque.

## Tres modelos, una base de código

No se mantienen tres `src`. `model_name` se resuelve contra el registro y el
runtime reutiliza un cliente asíncrono por endpoint. El agente envía siempre el
`served_model` canónico, por lo que alias históricos no se filtran al proveedor.

El registro es parte del artefacto versionado y permite revisar cambios de
checkpoint y capacidades. Las URL y claves quedan fuera porque son secretos y
varían entre ambientes. El endpoint `/v1/models` expone metadatos seguros, nunca
las URL ni las claves.

## Concurrencia

La API no conserva jobs ni posiciones en una cola. Un semáforo limita solicitudes
activas y devuelve `429` con `Retry-After` al saturarse. RunPod y vLLM administran
escalado, espera de workers y continuous batching en los endpoints de modelo.

## Selección y ciclo de vida

No se cargan ni descargan modelos en la API. En Serverless, cada endpoint vLLM
tiene su propio ciclo de vida. Elegir `qwen`, `glm` o `llama` solo cambia el
destino remoto. Esto evita que una réplica del agente necesite memoria GPU para
tres checkpoints o que un cambio de pesos bloquee consultas activas.

## Seguridad

- contenedor sin root y sin modelos ni credenciales embebidas;
- comparación de la API key del agente en tiempo constante;
- secretos independientes por endpoint;
- scripts en lista cerrada, entrada JSON, timeout y tamaño de salida limitado;
- snapshot de solo lectura, sin acceso a la base de datos;
- `/ready` valida configuración sin despertar modelos ni filtrar secretos.

## RAG y cold starts

Los doce documentos aprobados se validan e insertan de forma idempotente al
arrancar. La base es efímera por diseño. Una ingesta dinámica futura requerirá
almacenamiento externo compartido; no se ofrece una escritura que diverja entre
réplicas.

## ValidSintaxis, YAKE y respuesta

La reorganización conserva todos los scripts de la skill. `ValidSintaxis`
devuelve únicamente capacidades presentes en el snapshot y YAKE extrae términos
con relevancia normalizada. El contrato Pydantic exige una justificación por
cadena basada en cobertura de revistas, áreas/programas y capacidades reales de
la plataforma, no una narración del razonamiento interno.

## Límites conocidos

Los tres checkpoints históricos quedaron declarados, pero el parser de tool
calling es una propiedad del vLLM desplegado. Qwen y Llama tienen configuraciones
conocidas; GLM-4-9B debe validarse en la versión elegida de vLLM antes de tráfico
real. Si no ofrece tool calls OpenAI confiables, debe actualizarse esa entrada a
un GLM soportado sin duplicar el código del agente.
