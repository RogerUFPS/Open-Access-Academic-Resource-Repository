"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  Clock,
  Loader2,
  Maximize2,
  MessageSquarePlus,
  RefreshCw,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import ChatResponseView from "@/shared/components/ChatResponseView";
import useRetryCountdown, { formatWait } from "@/shared/hooks/useRetryCountdown";
import {
  clearChatSession,
  computeNextPollDelayMs,
  createConversation,
  describeChatError,
  generateClientMessageId,
  getAllMessages,
  getTurn,
  isTurnPending,
  loadChatSession,
  mergeTurn,
  PROMPT_MAX_LENGTH,
  PROMPT_MIN_LENGTH,
  saveChatSession,
  submitMessage,
  validatePrompt,
} from "@/features/public/agent/chatService";

const STARTER_PROMPTS = [
  "Revistas sobre inteligencia artificial para ingeniería de sistemas",
  "Bases de datos de acceso abierto sobre energías renovables en inglés",
  "Recursos académicos sobre salud pública y epidemiología",
];

function formatElapsed(seconds) {
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}

export default function AgentPanel({ compact = false, onClose = null, expandHref = "/asistente" }) {
  const [session, setSession] = useState(null);
  const [turns, setTurns] = useState([]);
  const [hydrating, setHydrating] = useState(true);
  const [draft, setDraft] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [activeTurnId, setActiveTurnId] = useState(null);
  const [pollState, setPollState] = useState({ turnId: null, status: "idle", notice: "" });
  const [pollRestartTick, setPollRestartTick] = useState(0);
  const [elapsedState, setElapsedState] = useState({ turnId: null, seconds: 0 });
  const [errorBanner, setErrorBanner] = useState(null);

  const { remaining, limited, handleRateLimit } = useRetryCountdown();
  const draftMessageIdRef = useRef(null);
  const scrollEndRef = useRef(null);
  const textareaRef = useRef(null);

  // Hidrata la conversación guardada en sessionStorage al montar (solo navegador).
  useEffect(() => {
    const controller = new AbortController();

    async function restoreHistory() {
      await Promise.resolve();
      if (controller.signal.aborted) return;

      const stored = loadChatSession();
      if (!stored) {
        setHydrating(false);
        return;
      }

      setSession(stored);

      try {
        const history = await getAllMessages({
          conversationId: stored.id,
          accessToken: stored.access_token,
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;

        setTurns(history);
        const pendingTurn = [...history].reverse().find(isTurnPending);
        const resumeTurnId = pendingTurn?.id ?? stored.pendingTurnId ?? null;

        if (resumeTurnId && (!pendingTurn || isTurnPending(pendingTurn))) {
          setActiveTurnId(String(resumeTurnId));
          saveChatSession({ ...stored, pendingTurnId: String(resumeTurnId) });
        } else {
          setActiveTurnId(null);
          saveChatSession({ ...stored, pendingTurnId: null });
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error?.status === 404) {
          clearChatSession();
          setSession(null);
          setTurns([]);
          setActiveTurnId(null);
          setErrorBanner({
            tone: "info",
            message: "Tu conversación anterior ya no está disponible. Puedes iniciar una nueva consulta.",
          });
        } else {
          setErrorBanner({
            tone: "warning",
            message: describeChatError(error),
          });
          if (stored.pendingTurnId) {
            setActiveTurnId(stored.pendingTurnId);
          }
        }
      } finally {
        if (!controller.signal.aborted) {
          setHydrating(false);
        }
      }
    }

    restoreHistory();
    return () => controller.abort();
  }, []);

  // Polling con backoff (2s hasta 10s) respetando Retry-After mientras el turno esté queued o running.
  useEffect(() => {
    if (!session?.id || !session?.access_token || !activeTurnId) {
      return undefined;
    }

    const controller = new AbortController();
    const currentTurnId = activeTurnId;
    let timerId = null;
    let attempt = 0;

    async function pollOnce() {
      if (controller.signal.aborted) return;
      try {
        const { turn, retryAfter } = await getTurn({
          conversationId: session.id,
          accessToken: session.access_token,
          turnId: currentTurnId,
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;

        setTurns((current) => mergeTurn(current, turn));

        if (isTurnPending(turn)) {
          setPollState({ turnId: currentTurnId, status: "polling", notice: "" });
          const delay = computeNextPollDelayMs(attempt, retryAfter);
          attempt += 1;
          timerId = window.setTimeout(pollOnce, delay);
        } else {
          setActiveTurnId(null);
          setPollState({ turnId: null, status: "idle", notice: "" });
          saveChatSession({ ...session, pendingTurnId: null });
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error?.status === 404) {
          clearChatSession();
          setSession(null);
          setActiveTurnId(null);
          setPollState({ turnId: null, status: "idle", notice: "" });
          setErrorBanner({
            tone: "info",
            message: describeChatError(error),
          });
          return;
        }
        // Error temporal, 429 o timeout: conservar el turno y reintentar el polling con backoff.
        setPollState({ turnId: currentTurnId, status: "reconnecting", notice: describeChatError(error) });
        const delay = computeNextPollDelayMs(attempt, error?.retryAfter);
        attempt += 1;
        timerId = window.setTimeout(pollOnce, delay);
      }
    }

    timerId = window.setTimeout(pollOnce, computeNextPollDelayMs(0, null));

    return () => {
      controller.abort();
      if (timerId !== null) window.clearTimeout(timerId);
    };
  }, [session, activeTurnId, pollRestartTick]);

  // Contador de tiempo transcurrido mientras el turno está en curso (útil durante arranque en frío).
  useEffect(() => {
    if (!activeTurnId) {
      return undefined;
    }
    const currentTurnId = activeTurnId;
    const startedAt = Date.now();
    const intervalId = window.setInterval(() => {
      setElapsedState({ turnId: currentTurnId, seconds: Math.floor((Date.now() - startedAt) / 1000) });
    }, 1000);
    return () => window.clearInterval(intervalId);
  }, [activeTurnId]);

  const pollStatus = activeTurnId && pollState.turnId === activeTurnId ? pollState.status : activeTurnId ? "polling" : "idle";
  const pollNotice = activeTurnId && pollState.turnId === activeTurnId ? pollState.notice : "";
  const elapsedSeconds = activeTurnId && elapsedState.turnId === activeTurnId ? elapsedState.seconds : 0;

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, activeTurnId]);

  const hasPendingTurn = Boolean(activeTurnId) || turns.some(isTurnPending);
  const trimmedDraft = draft.trim();
  const isBusy = submitting || hasPendingTurn || hydrating;

  function handleDraftChange(nextValue) {
    setDraft(nextValue);
    if (errorBanner?.tone === "error") {
      setErrorBanner(null);
    }
    if (draftMessageIdRef.current && draftMessageIdRef.current.prompt !== nextValue.trim()) {
      draftMessageIdRef.current = null;
    }
  }

  function handleResetConversation() {
    clearChatSession();
    draftMessageIdRef.current = null;
    setSession(null);
    setTurns([]);
    setActiveTurnId(null);
    setPollState({ turnId: null, status: "idle", notice: "" });
    setElapsedState({ turnId: null, seconds: 0 });
    setErrorBanner(null);
    textareaRef.current?.focus();
  }

  async function handleSubmit(event, overridePrompt = null) {
    if (event) event.preventDefault();
    if (isBusy || limited) return;

    const rawText = overridePrompt !== null ? overridePrompt : draft;
    const validation = validatePrompt(rawText);
    if (!validation.valid) {
      setErrorBanner({ tone: "error", message: validation.error });
      return;
    }

    const prompt = validation.prompt;
    // Conserva el mismo UUID v4 al reintentar el mismo mensaje.
    let clientMessageId;
    if (draftMessageIdRef.current?.prompt === prompt) {
      clientMessageId = draftMessageIdRef.current.id;
    } else {
      clientMessageId = generateClientMessageId();
      draftMessageIdRef.current = { prompt, id: clientMessageId };
    }

    setSubmitting(true);
    setErrorBanner(null);

    try {
      let currentSession = session;
      if (!currentSession) {
        const created = await createConversation();
        currentSession = {
          id: String(created.id),
          access_token: String(created.access_token),
          pendingTurnId: null,
        };
        saveChatSession(currentSession);
        setSession(currentSession);
      }

      const { turn } = await submitMessage({
        conversationId: currentSession.id,
        accessToken: currentSession.access_token,
        prompt,
        clientMessageId,
      });

      draftMessageIdRef.current = null;
      setDraft("");
      setTurns((current) => mergeTurn(current, turn));

      if (isTurnPending(turn)) {
        const nextTurnId = String(turn.id);
        setActiveTurnId(nextTurnId);
        saveChatSession({ ...currentSession, pendingTurnId: nextTurnId });
      } else {
        setActiveTurnId(null);
        saveChatSession({ ...currentSession, pendingTurnId: null });
      }
    } catch (error) {
      if (error?.status === 404) {
        clearChatSession();
        setSession(null);
        setActiveTurnId(null);
        setErrorBanner({
          tone: "warning",
          message: describeChatError(error),
        });
      } else if (error?.status === 409 || error?.code === "conversation_busy") {
        setErrorBanner({
          tone: "warning",
          message: describeChatError(error),
        });
        if (session?.id && session?.access_token) {
          try {
            const refreshed = await getAllMessages({
              conversationId: session.id,
              accessToken: session.access_token,
            });
            setTurns(refreshed);
            const running = [...refreshed].reverse().find(isTurnPending);
            if (running?.id) {
              const runningId = String(running.id);
              setActiveTurnId(runningId);
              saveChatSession({ ...session, pendingTurnId: runningId });
            }
          } catch {
            // Mantener el aviso de 409 si falla la sincronización.
          }
        }
      } else if (handleRateLimit(error)) {
        setErrorBanner({
          tone: "warning",
          message: describeChatError(error),
        });
      } else if (error?.status === 503) {
        setErrorBanner({
          tone: "warning",
          message: describeChatError(error),
        });
      } else {
        setErrorBanner({
          tone: "error",
          message: describeChatError(error),
        });
      }
    } finally {
      setSubmitting(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(null);
    }
  }

  return (
    <section
      aria-label="Asistente de búsqueda académica"
      className={`flex flex-col overflow-hidden bg-white ${
        compact
          ? "h-full rounded-none sm:rounded-xl"
          : "min-h-[600px] rounded-xl border border-[#e7dfd9] shadow-[0_12px_36px_rgba(54,35,28,0.06)]"
      }`}
    >
      {/* Cabecera */}
      <header className="flex items-center justify-between gap-3 border-b border-[#e7dfd9] bg-[#7f1218] px-4 py-3.5 text-white sm:px-5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white/15">
            <Sparkles className="h-4 w-4 text-[#f5d79b]" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-bold sm:text-base">Asistente de búsqueda académica</h2>
            <p className="truncate text-xs text-white/80">
              Chat anónimo · Estrategias y cadenas para bases de datos y revistas
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {turns.length > 0 && (
            <button
              type="button"
              onClick={handleResetConversation}
              disabled={submitting}
              title="Iniciar una nueva conversación"
              className="inline-flex items-center gap-1.5 rounded-md border border-white/25 bg-white/10 px-2.5 py-1.5 text-xs font-semibold text-white transition hover:bg-white/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white disabled:opacity-50"
            >
              <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden="true" />
              <span className={compact ? "sr-only sm:not-sr-only" : ""}>Nuevo chat</span>
            </button>
          )}
          {compact && expandHref && (
            <Link
              href={expandHref}
              onClick={onClose || undefined}
              title="Abrir en pantalla completa"
              aria-label="Abrir asistente en pantalla completa"
              className="grid h-8 w-8 place-items-center rounded-md text-white/85 transition hover:bg-white/15 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            >
              <Maximize2 className="h-4 w-4" aria-hidden="true" />
            </Link>
          )}
          {compact && onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Cerrar asistente"
              className="grid h-8 w-8 place-items-center rounded-md text-white/85 transition hover:bg-white/15 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
      </header>

      {/* Historial de mensajes */}
      <div
        className={`flex-1 space-y-4 overflow-y-auto bg-[#faf7f4] px-4 py-5 sm:px-6 ${
          compact ? "min-h-0" : "max-h-[65vh] min-h-[380px]"
        }`}
      >
        {hydrating ? (
          <div role="status" className="flex items-center justify-center gap-2 py-12 text-sm text-[#5c5252]">
            <Loader2 className="h-4 w-4 animate-spin text-[#a3141c]" aria-hidden="true" />
            <span>Recuperando tu conversación…</span>
          </div>
        ) : turns.length === 0 ? (
          <div className="mx-auto max-w-xl space-y-5 py-4 text-center sm:py-8">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-[#7f1218]/10 text-[#7f1218]">
              <Sparkles className="h-6 w-6" aria-hidden="true" />
            </div>
            <div className="space-y-1.5">
              <h3 className="text-lg font-bold text-[#1f1a1a]">
                ¿Qué tema académico deseas investigar?
              </h3>
              <p className="text-sm leading-6 text-[#5c5252]">
                Describe tu tema, programa académico o idioma de interés. El asistente te sugerirá plataformas del
                directorio con cadenas de búsqueda listas para usar.
              </p>
            </div>
            <div className="space-y-2 text-left">
              <p className="text-xs font-bold uppercase tracking-wider text-[#5c5252]">
                Ejemplos para empezar
              </p>
              <div className="grid gap-2">
                {STARTER_PROMPTS.map((example) => (
                  <button
                    key={example}
                    type="button"
                    disabled={isBusy || limited}
                    onClick={() => handleSubmit(null, example)}
                    className="rounded-lg border border-[#e7dfd9] bg-white px-3.5 py-2.5 text-left text-sm text-[#1f1a1a] transition hover:border-[#a3141c] hover:text-[#a3141c] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#a3141c] disabled:opacity-50"
                  >
                    “{example}”
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            {turns.map((turn, index) => {
              const pending = isTurnPending(turn);
              const turnKey = turn.id ?? turn.client_message_id ?? `turn-${index}`;

              return (
                <div key={turnKey} className="space-y-3">
                  {/* Mensaje del usuario (siempre texto escapado) */}
                  <div className="flex justify-end">
                    <div className="max-w-[88%] rounded-2xl rounded-br-sm bg-[#7f1218] px-4 py-3 text-sm leading-6 text-white shadow-xs sm:max-w-[78%]">
                      <p className="whitespace-pre-wrap break-words">{turn.prompt}</p>
                    </div>
                  </div>

                  {/* Respuesta del asistente */}
                  <div className="flex justify-start">
                    <div className="w-full max-w-[96%] rounded-2xl rounded-bl-sm border border-[#e7dfd9] bg-white p-4 shadow-xs sm:max-w-[88%]">
                      {pending ? (
                        <div role="status" aria-live="polite" className="space-y-2.5">
                          <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-[#1f1a1a]">
                            <Loader2 className="h-4 w-4 animate-spin text-[#a3141c]" aria-hidden="true" />
                            <span>
                              {turn.status === "running"
                                ? "Generando estrategias de búsqueda…"
                                : "Tu consulta está en cola…"}
                            </span>
                            {elapsedSeconds > 0 && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-[#faf7f4] px-2 py-0.5 text-xs text-[#5c5252]">
                                <Clock className="h-3 w-3" aria-hidden="true" />
                                {formatElapsed(elapsedSeconds)}
                              </span>
                            )}
                          </div>
                          {elapsedSeconds >= 12 && (
                            <p className="text-xs leading-5 text-[#5c5252]">
                              Si el modelo está iniciando en frío, la primera respuesta puede tardar varios minutos.
                              No hace falta reenviar tu pregunta; seguiremos consultando el estado automáticamente.
                            </p>
                          )}
                          {pollStatus === "reconnecting" && (
                            <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-[#f3d9a4] bg-[#fffaf0] px-3 py-2 text-xs text-[#7A4B00]">
                              <span>{pollNotice || "Reconectando para consultar el resultado…"}</span>
                              <button
                                type="button"
                                onClick={() => setPollRestartTick((tick) => tick + 1)}
                                className="inline-flex items-center gap-1 font-semibold underline"
                              >
                                <RefreshCw className="h-3 w-3" aria-hidden="true" />
                                Consultar ahora
                              </button>
                            </div>
                          )}
                        </div>
                      ) : (
                        <ChatResponseView
                          response={turn.response}
                          turnStatus={turn.status}
                          openPlatformInNewTab={compact}
                        />
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        <div ref={scrollEndRef} />
      </div>

      {/* Avisos de error o rate limit */}
      {(errorBanner || limited) && (
        <div className="border-t border-[#e7dfd9] bg-white px-4 pt-3 sm:px-5">
          <div
            role="alert"
            className={`flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 text-xs leading-5 ${
              errorBanner?.tone === "error"
                ? "border-[#f5c2c7] bg-[#fff5f5] text-[#820A1F]"
                : errorBanner?.tone === "info"
                  ? "border-[#dce0e5] bg-[#f7f8fa] text-[#374151]"
                  : "border-[#f3d9a4] bg-[#fffaf0] text-[#7A4B00]"
            }`}
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <div className="min-w-0 flex-1 space-y-1">
              {errorBanner?.message && <p>{errorBanner.message}</p>}
              {limited && (
                <p className="font-semibold">
                  Podrás reintentar en {formatWait(remaining)}. Tu consulta se conserva tal como la escribiste.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Formulario de entrada */}
      <form
        onSubmit={handleSubmit}
        className="border-t border-[#e7dfd9] bg-white px-4 py-3.5 sm:px-5"
      >
        <div className="flex items-end gap-2.5">
          <div className="min-w-0 flex-1">
            <label htmlFor={compact ? "widget-chat-prompt" : "page-chat-prompt"} className="sr-only">
              Escribe tu consulta académica
            </label>
            <textarea
              ref={textareaRef}
              id={compact ? "widget-chat-prompt" : "page-chat-prompt"}
              rows={compact ? 2 : 2}
              value={draft}
              onChange={(event) => handleDraftChange(event.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isBusy}
              maxLength={PROMPT_MAX_LENGTH + 50}
              placeholder={
                turns.length > 0
                  ? "Continúa la conversación (ej. «Y en inglés» o «Solo revistas»)…"
                  : "Describe tu tema de investigación, programa o idioma…"
              }
              className="block w-full resize-none rounded-lg border border-[#dcd3cc] bg-[#faf7f4] px-3.5 py-2.5 text-sm leading-5 text-[#1f1a1a] placeholder:text-[#6b6060] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#a3141c] disabled:cursor-not-allowed disabled:opacity-60"
            />
          </div>
          <button
            type="submit"
            disabled={isBusy || limited || trimmedDraft.length < PROMPT_MIN_LENGTH}
            className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-lg bg-[#a3141c] px-4 text-sm font-semibold text-white transition hover:bg-[#8a1018] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#a3141c] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Send className="h-4 w-4" aria-hidden="true" />
            )}
            <span className={compact ? "sr-only sm:not-sr-only" : ""}>Enviar</span>
          </button>
        </div>

        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-[#6b6060]">
          <span>
            Enter para enviar · Shift + Enter para salto de línea. Conversación anónima en esta pestaña.
          </span>
          {draft.length > 3200 && (
            <span className={trimmedDraft.length > PROMPT_MAX_LENGTH ? "font-semibold text-[#820A1F]" : ""}>
              {trimmedDraft.length} / {PROMPT_MAX_LENGTH}
            </span>
          )}
        </div>
      </form>
    </section>
  );
}
