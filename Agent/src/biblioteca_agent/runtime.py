"""Orquestación del modelo, RAG y herramientas."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from openai import AsyncOpenAI

from .config import RESOURCES_DIR, settings
from .contracts import QueryRequest, RecommendationResponse, model_registry
from .model_registry import ModelDefinition
from .rag import RagStore, read_jsonl
from .tool_runner import RAG_TOOL, SCRIPT_TOOL, run_script


class AgentRuntime:
    def __init__(self):
        self.clients: dict[str, AsyncOpenAI] = {}
        self.rag = RagStore(settings.rag_path)
        self.request_slots = asyncio.Semaphore(settings.max_concurrency)
        self.active_requests = 0
        self.runtime_prompt = (RESOURCES_DIR / "runtime_prompt.md").read_text(encoding="utf-8")

    async def start(self) -> None:
        if settings.auto_index_rag:
            documents = await asyncio.to_thread(
                read_jsonl, RESOURCES_DIR / "rag_examples.approved.jsonl"
            )
            await asyncio.to_thread(self.rag.upsert, documents)

    async def stop(self) -> None:
        await asyncio.gather(*(client.close() for client in self.clients.values()))
        self.clients.clear()

    def client_for(self, model: ModelDefinition) -> AsyncOpenAI:
        client = self.clients.get(model.name)
        if client is None:
            base_url, api_key = model.endpoint()
            client = AsyncOpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=settings.vllm_request_timeout_seconds,
                max_retries=2,
            )
            self.clients[model.name] = client
        return client

    async def run(self, request: QueryRequest) -> dict[str, Any]:
        model = model_registry.get(request.model_name)
        client = self.client_for(model)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "Sigue las instrucciones operativas. Usa herramientas para obtener todos los datos; "
                    "no inventes ids ni capacidades. El RAG contiene ejemplos, no hechos del catálogo. "
                    "Justifica la selección con cobertura y capacidades, no con pasos internos.\n\n"
                    + self.runtime_prompt
                ),
            },
            {"role": "user", "content": request.prompt},
        ]
        for _ in range(settings.max_tool_rounds):
            response = await client.chat.completions.create(
                model=model.served_model,
                messages=messages,
                tools=[SCRIPT_TOOL, RAG_TOOL],
                tool_choice="auto",
                parallel_tool_calls=False,
                temperature=0,
                max_tokens=settings.vllm_max_tokens,
                extra_body=model.request_options,
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []
            serialized: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
            if tool_calls:
                serialized["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in tool_calls
                ]
            messages.append(serialized)
            if not tool_calls:
                try:
                    return self.parse_final(message.content or "")
                except (json.JSONDecodeError, ValueError):
                    messages.append({
                        "role": "user",
                        "content": (
                            "La respuesta no cumple el contrato JSON final. Corrígela sin ejecutar "
                            "herramientas y responde solo con el objeto JSON."
                        ),
                    })
                    continue
            for call in tool_calls:
                arguments = call.function.arguments or "{}"
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if call.function.name == "run_python_script":
                    output = await asyncio.to_thread(
                        run_script,
                        arguments.get("script_name", ""),
                        arguments.get("script_args", {}),
                    )
                elif call.function.name == "rag_search":
                    output = await asyncio.to_thread(
                        self.rag.search,
                        str(arguments.get("query", "")),
                        int(arguments.get("limit", 3)),
                    )
                else:
                    output = {"error": "Herramienta no permitida."}
                messages.append({
                    "role": "tool",
                    "content": json.dumps(output, ensure_ascii=False),
                    "tool_call_id": call.id,
                })
        raise RuntimeError("El modelo excedió el límite de llamadas a herramientas.")

    @staticmethod
    def parse_final(content: str) -> dict[str, Any]:
        return RecommendationResponse.model_validate_json(content).model_dump()
