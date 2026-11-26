import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("@/")) {
      return nextResolve(new URL(`../src/${specifier.slice(2)}.js`, import.meta.url).href, context);
    }
    return nextResolve(specifier, context);
  },
});

const chatService = await import("../src/features/public/agent/chatService.js");
const adminService = await import("../src/features/admin/agent/agentAdminService.js");

function jsonResponse(body, { status = 200, headers = {} } = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

test("public chat creates anonymous conversation with credentials: omit and empty JSON object", async () => {
  const calls = [];
  const mockFetch = async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(
      {
        id: "conv-123",
        created_at: "2026-11-20T12:00:00Z",
        updated_at: "2026-11-20T12:00:00Z",
        has_unclear: false,
        turn_count: 0,
        access_token: "secret-chat-token",
      },
      { status: 201 },
    );
  };

  const created = await chatService.createConversation(undefined, mockFetch);
  assert.equal(created.id, "conv-123");
  assert.equal(created.access_token, "secret-chat-token");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/agent/chat/conversations/");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.credentials, "omit");
  assert.equal(calls[0].options.body, "{}");
});

test("public chat submits message with X-Chat-Token, credentials: omit, and supports 202 and 200 retries", async () => {
  const calls = [];
  const token = "one-time-secret-token";
  const clientMessageId = chatService.generateClientMessageId();
  assert.match(clientMessageId, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);

  const mockFetch = async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(
      {
        id: "turn-1",
        client_message_id: clientMessageId,
        sequence: 1,
        prompt: "Revistas de IA",
        status: calls.length === 1 ? "queued" : "completed",
        response: calls.length === 1 ? null : { estado: "ok", mensaje: null, busquedas: [], filtros_no_aplicados: [] },
      },
      { status: calls.length === 1 ? 202 : 200 },
    );
  };

  const first = await chatService.submitMessage(
    { conversationId: "conv-1", accessToken: token, prompt: "Revistas de IA", clientMessageId },
    mockFetch,
  );
  assert.equal(first.status, 202);
  assert.equal(chatService.isTurnPending(first.turn), true);
  assert.equal(calls[0].options.credentials, "omit");
  assert.equal(calls[0].options.headers["X-Chat-Token"], token);
  assert.equal(calls[0].url.includes(token), false);

  const retry = await chatService.submitMessage(
    { conversationId: "conv-1", accessToken: token, prompt: "Revistas de IA", clientMessageId },
    mockFetch,
  );
  assert.equal(retry.status, 200);
  assert.equal(chatService.isTurnPending(retry.turn), false);
});

test("public chat polling backoff scales from 2s to 10s and always respects Retry-After", () => {
  assert.equal(chatService.computeNextPollDelayMs(0, null), 2000);
  assert.ok(chatService.computeNextPollDelayMs(1, null) > 2000);
  assert.equal(chatService.computeNextPollDelayMs(10, null), 10000);
  assert.equal(chatService.computeNextPollDelayMs(0, 7), 7000);
  assert.equal(chatService.computeNextPollDelayMs(5, 15), 15000);
});

test("public chat reads all paginated history pages and sorts by sequence", async () => {
  const mockFetch = async (url, options) => {
    assert.equal(options.credentials, "omit");
    assert.equal(options.headers["X-Chat-Token"], "tok");
    if (url.includes("page=1")) {
      return jsonResponse({
        current_page: 1,
        total_pages: 2,
        page_size: 20,
        total_items: 3,
        next: "/api/agent/chat/conversations/c1/messages/?page=2&page_size=20",
        previous: null,
        results: [
          { id: "t2", sequence: 2, prompt: "Y en inglés", status: "completed" },
          { id: "t1", sequence: 1, prompt: "Revistas de IA", status: "completed" },
        ],
      });
    }
    return jsonResponse({
      current_page: 2,
      total_pages: 2,
      page_size: 20,
      total_items: 3,
      next: null,
      previous: "/api/agent/chat/conversations/c1/messages/?page=1&page_size=20",
      results: [{ id: "t3", sequence: 3, prompt: "Solo acceso abierto", status: "running" }],
    });
  };

  const turns = await chatService.getAllMessages(
    { conversationId: "c1", accessToken: "tok" },
    mockFetch,
  );
  assert.deepEqual(
    turns.map((turn) => turn.id),
    ["t1", "t2", "t3"],
  );
});

test("public chat maps HTTP errors 400, 404, 409, 429 and 503 without leaking tokens", async () => {
  const secret = "super-secret-chat-token-xyz";
  const cases = [
    { status: 400, body: { prompt: ["Debe tener al menos 3 caracteres."] }, expectedCode: null },
    { status: 404, body: { detail: "No encontrado" }, expectedCode: null },
    { status: 409, body: { code: "conversation_busy" }, expectedCode: "conversation_busy" },
    { status: 429, body: { code: "agent_busy" }, headers: { "Retry-After": "12" }, expectedCode: "agent_busy", retryAfter: 12 },
    { status: 503, body: { code: "model_switch_pending" }, expectedCode: "model_switch_pending" },
    { status: 503, body: { code: "agent_unavailable" }, expectedCode: "agent_unavailable" },
  ];

  for (const item of cases) {
    const mockFetch = async () => jsonResponse(item.body, { status: item.status, headers: item.headers });
    await assert.rejects(
      chatService.submitMessage(
        { conversationId: "c1", accessToken: secret, prompt: "Consulta de prueba", clientMessageId: "uuid-1" },
        mockFetch,
      ),
      (error) => {
        assert.equal(error.status, item.status);
        assert.equal(error.code, item.expectedCode);
        if (item.retryAfter) assert.equal(error.retryAfter, item.retryAfter);
        assert.equal(error.message.includes(secret), false);
        assert.ok(error.message.length > 0);
        return true;
      },
    );
  }
});

test("admin agent permission checks respect superadmin and granular agent keys", () => {
  assert.equal(adminService.hasAgentPermission({ is_superadmin: true }, "models", "update"), true);
  assert.equal(
    adminService.hasAgentPermission({ effective_permissions: { agent: { models: { view: true } } } }, "models", "view"),
    true,
  );
  assert.equal(
    adminService.hasAgentPermission({ effective_permissions: { agent: { models: { view: true } } } }, "models", "update"),
    false,
  );
  assert.equal(
    adminService.hasAgentPermission({ effective_permissions: { agent: { analytics: { view: true } } } }, "conversations", "view"),
    false,
  );
});

test("admin model target is only considered active when active_model matches, pending_model is null, and phase is ready", () => {
  assert.equal(
    adminService.isTargetActivated({ active_model: "glm", pending_model: null, phase: "ready" }, "glm"),
    true,
  );
  assert.equal(
    adminService.isTargetActivated({ active_model: "qwen", pending_model: "glm", phase: "draining" }, "glm"),
    false,
  );
  assert.equal(
    adminService.isTargetActivated({ active_model: "glm", pending_model: "llama", phase: "switching" }, "glm"),
    false,
  );
  assert.equal(
    adminService.isTargetActivated({ active_model: "glm", pending_model: null, phase: "error" }, "glm"),
    false,
  );
});

test("admin model mutations send expected payloads (switch with model, cancel without body)", async () => {
  const calls = [];
  const api = adminService.createAgentMutations(async (path, method, body) => {
    calls.push({ path, method, body });
    if (path.endsWith("/switch/")) return { status: 202, data: { pending_model: "glm", phase: "draining" } };
    return { status: 200, data: { active_model: "qwen", pending_model: null, phase: "ready" } };
  });

  const switched = await api.switchModel("glm");
  assert.equal(switched.status, 202);
  assert.deepEqual(calls[0], { path: "/api/agent/models/switch/", method: "POST", body: { model: "glm" } });

  const cancelled = await api.cancelModelSwitch();
  assert.equal(cancelled.status, 200);
  assert.deepEqual(calls[1], { path: "/api/agent/models/cancel/", method: "POST", body: undefined });
});

test("admin conversation detail normalizer handles top-level pagination and nested turns", () => {
  const topLevel = adminService.normalizeConversationDetail(
    {
      current_page: 1,
      total_pages: 2,
      page_size: 20,
      total_items: 25,
      results: [{ id: "t1", sequence: 1, model_name: "qwen", unclear: true }],
    },
    "conv-99",
  );
  assert.equal(topLevel.conversation.id, "conv-99");
  assert.equal(topLevel.conversation.has_unclear, true);
  assert.equal(topLevel.turns.totalItems, 25);
  assert.equal(topLevel.turns.totalPages, 2);
});

test("analytics range validation enforces limit 1-100 and since <= until", () => {
  assert.equal(adminService.validateAnalyticsRange({ limit: 20, since: "2026-01-01", until: "2026-12-31" }).valid, true);
  assert.equal(adminService.validateAnalyticsRange({ limit: 0 }).valid, false);
  assert.equal(adminService.validateAnalyticsRange({ limit: 101 }).valid, false);
  assert.equal(adminService.validateAnalyticsRange({ limit: 20, since: "2026-12-31", until: "2026-01-01" }).valid, false);
});
