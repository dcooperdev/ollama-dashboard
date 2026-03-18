import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Square, User, Bot, AlertTriangle, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { streamPost } from '../../api/client.js';
import RecommendationCard from './RecommendationCard.jsx';

/**
 * AgentChat — a ChatGPT-style conversational interface with streaming responses.
 *
 * Key implementation details:
 *  - Messages are stored as { id, role, content, error? } objects.
 *  - When sending, a placeholder assistant message is added immediately; its
 *    content is updated token-by-token via functional setState to avoid
 *    stale-closure issues inside the SSE callback.
 *  - An AbortController is created per request and its signal is passed to
 *    streamPost() so the fetch stream is cancelled if the user clicks Stop or
 *    the component unmounts while a response is generating.
 *  - Auto-scroll tracks whether the user is near the bottom; if so, the view
 *    follows new tokens. If the user has scrolled up manually, we respect that.
 *
 * @param {{ model: string }} props
 */
export default function AgentChat({ model }) {
    // Derive a stable sessionStorage key for this model's conversation.
    const storageKey = `chat_history_${model}`;

    const [messages, setMessages] = useState(() => {
        // Lazy initializer: restore messages from sessionStorage on mount so
        // navigating away from the Playground and back does not wipe the chat.
        try {
            const saved = sessionStorage.getItem(storageKey);
            return saved ? JSON.parse(saved) : [];
        } catch {
            // Malformed JSON or quota errors — start fresh.
            return [];
        }
    });
    const [input, setInput] = useState('');
    const [streaming, setStreaming] = useState(false);
    // Name of the specialist model currently being consulted, or null when idle.
    const [consultingTarget, setConsultingTarget] = useState(null);
    // Human-in-the-Loop Recommendation state object: { target, reason }
    const [recommendation, setRecommendation] = useState(null);

    const abortRef = useRef(null);        // AbortController for the current stream
    const containerRef = useRef(null);    // scrollable message container
    const inputRef = useRef(null);        // textarea ref for focus management
    const atBottomRef = useRef(true);     // tracks if user is scrolled to the bottom

    // ---- Auto-scroll --------------------------------------------------------

    // Keep track of whether the user is near the bottom of the chat.
    const handleScroll = useCallback(() => {
        const el = containerRef.current;
        if (!el) return;
        atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
    }, []);

    // Scroll to the bottom whenever the last message's content changes (i.e., on
    // each streaming token) but only if the user hasn't scrolled up manually.
    useEffect(() => {
        if (atBottomRef.current && containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
    }, [messages]);

    // Always scroll to bottom when a new message is added (user send or new AI reply).
    const scrollToBottom = () => {
        if (containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight;
            atBottomRef.current = true;
        }
    };

    // Persist the conversation to sessionStorage whenever messages change.
    // This keeps history alive across navigation within the same browser session.
    useEffect(() => {
        try {
            sessionStorage.setItem(storageKey, JSON.stringify(messages));
        } catch {
            // Quota exceeded or privacy mode — silently ignore.
        }
    }, [messages, storageKey]);

    // ---- Cleanup on unmount -------------------------------------------------

    useEffect(() => {
        return () => {
            // Cancel any in-flight request when the component is destroyed (e.g. model
            // switch triggers a remount via the key prop in Playground).
            abortRef.current?.abort();
        };
    }, []);

    // ---- Send message -------------------------------------------------------

    const sendMessage = useCallback(async () => {
        if (!input.trim() || streaming || !model) return;

        const userContent = input.trim();
        setInput('');

        // Build the new user message and an empty placeholder for the assistant reply.
        const uid = Date.now();
        const aid = uid + 1;

        const userMsg = { id: uid, role: 'user', content: userContent };
        const assistMsg = { id: aid, role: 'assistant', content: '', streaming: true };

        setMessages((prev) => [...prev, userMsg, assistMsg]);
        scrollToBottom();
        setStreaming(true);

        // Build the message history to send (exclude the placeholder assistant msg).
        const historyForApi = [...messages, userMsg].map(({ role, content }) => ({
            role,
            content,
        }));

        abortRef.current = new AbortController();

        try {
            await streamPost(
                '/api/chat',
                { model, messages: historyForApi },
                (event) => {
                    if (event.token) {
                        // Append the token to the last assistant message in the list.
                        setMessages((prev) => {
                            const updated = [...prev];
                            const last = updated[updated.length - 1];
                            return [
                                ...updated.slice(0, -1),
                                { ...last, content: last.content + event.token },
                            ];
                        });
                    }
                    if (event.error) {
                        // Replace the assistant placeholder with a styled system-error
                        // message so the user clearly understands the failure reason.
                        setMessages((prev) => [
                            ...prev.slice(0, -1),
                            { id: aid, role: 'system-error', content: event.error },
                        ]);
                    }
                    // Meta-agent consulting status: show the animated badge.
                    if (event.status === 'consulting') {
                        setConsultingTarget(event.target ?? 'specialist');
                    }
                    if (event.status === 'recommendation') {
                        setRecommendation({ target: event.target_model, reason: event.reason });
                    }
                },
                abortRef.current.signal,
            );
        } catch (err) {
            if (err.name !== 'AbortError') {
                setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    return [
                        ...updated.slice(0, -1),
                        { ...last, error: `Connection error: ${err.message}`, content: last.content },
                    ];
                });
            }
        } finally {
            // Mark the assistant message as done — removes the streaming cursor.
            setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                return [...updated.slice(0, -1), { ...last, streaming: false }];
            });
            setStreaming(false);
            setConsultingTarget(null); // Reset consulting target
            inputRef.current?.focus();
        }
    }, [input, streaming, model, messages]);

    /** Stop the current generation. */
    const stopGeneration = () => {
        abortRef.current?.abort();
    };

    /** Submit on Enter (Shift+Enter inserts a newline). */
    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    /** Clear the conversation history and remove it from sessionStorage. */
    const clearChat = () => {
        abortRef.current?.abort();
        setMessages([]);
        sessionStorage.removeItem(storageKey);
        setStreaming(false);
        setConsultingTarget(null);
        setRecommendation(null);
        inputRef.current?.focus();
    };

    /** 
     * Resubmit the last user message, used by Human-in-the-Loop actions.
     * @param {string} overrideModel - The target model to route the request to.
     * @param {boolean} skipRouting - If true, bypasses the interceptor logic.
     */
    const resubmitMessage = useCallback(async (overrideModel, skipRouting) => {
        if (streaming) return;

        // Find the last user message to resubmit
        const historyForApi = messages.filter(m => !m.streaming && m.role !== 'system-error').map(({ role, content }) => ({
            role,
            content,
        }));

        if (historyForApi.length === 0) return;

        setRecommendation(null);
        setStreaming(true);
        scrollToBottom();

        const uid = Date.now();
        const aid = uid + 1;
        const assistMsg = { id: aid, role: 'assistant', content: '', streaming: true };
        setMessages((prev) => [...prev, assistMsg]);

        abortRef.current = new AbortController();

        try {
            await streamPost(
                '/api/chat',
                { model: overrideModel, messages: historyForApi, skip_routing: skipRouting },
                (event) => {
                    if (event.token) {
                        setMessages((prev) => {
                            const updated = [...prev];
                            const last = updated[updated.length - 1];
                            return [
                                ...updated.slice(0, -1),
                                { ...last, content: last.content + event.token },
                            ];
                        });
                    }
                    if (event.error) {
                        setMessages((prev) => [
                            ...prev.slice(0, -1),
                            { id: aid, role: 'system-error', content: event.error },
                        ]);
                    }
                    if (event.status === 'consulting') {
                        setConsultingTarget(event.target ?? 'specialist');
                    }
                    if (event.status === 'recommendation') {
                        setRecommendation({ target: event.target_model, reason: event.reason });
                    }
                },
                abortRef.current.signal,
            );
        } catch (err) {
            if (err.name !== 'AbortError') {
                setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    return [
                        ...updated.slice(0, -1),
                        { ...last, error: `Connection error: ${err.message}`, content: last.content },
                    ];
                });
            }
        } finally {
            setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                return [...updated.slice(0, -1), { ...last, streaming: false }];
            });
            setStreaming(false);
            setConsultingTarget(null);
            inputRef.current?.focus();
        }
    }, [messages, streaming]);

    // ---- Render -------------------------------------------------------------

    return (
        <div className="flex flex-col h-full min-h-0">
            {/* Message list */}
            <div
                ref={containerRef}
                onScroll={handleScroll}
                className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-5 min-h-0"
            >
                {/* Empty state */}
                {messages.length === 0 && (
                    <div className="flex-1 flex flex-col items-center justify-center
                          text-center animate-fade-in">
                        <div
                            className="w-14 h-14 rounded-2xl bg-accent/10 border border-accent/20
                            flex items-center justify-center mb-4"
                        >
                            <Bot size={26} className="text-accent-light" />
                        </div>
                        <p className="text-sm font-semibold text-txt-secondary">
                            Chat with{' '}
                            <span className="text-accent-light font-mono text-xs">{model}</span>
                        </p>
                        <p className="text-xs text-txt-muted mt-1">
                            Your messages support Markdown — try code blocks, lists, and tables.
                        </p>
                    </div>
                )}

                {/* Conversation */}
                {messages.map((msg) =>
                    msg.role === 'system-error' ? (
                        <SystemErrorMessage key={msg.id} message={msg.content} />
                    ) : (
                        <MessageBubble key={msg.id} message={msg} />
                    )
                )}
                {/* Human-in-the-Loop Recommendation */}
                {recommendation && (
                    <RecommendationCard
                        target={recommendation.target}
                        reason={recommendation.reason}
                        onInstallSuccess={(target) => resubmitMessage(target, false)}
                        onSkip={() => resubmitMessage(model, true)}
                    />
                )}
            </div>

            {/* Input bar */}
            <div className="shrink-0 px-6 py-4 border-t border-white/[0.05] bg-surface-base/40">
                {/* Animated badge shown while the primary model consults a specialist */}
                {consultingTarget && (
                    <ConsultingBadge target={consultingTarget} />
                )}
                {/* Clear button (only visible when there are messages) */}
                {messages.length > 0 && !streaming && (
                    <div className="mb-2 flex justify-end">
                        <button onClick={clearChat} className="btn-ghost text-xs py-1">
                            Clear chat
                        </button>
                    </div>
                )}

                <div className="flex gap-3 items-end">
                    <textarea
                        ref={inputRef}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder={`Message ${model}… (Shift+Enter for newline)`}
                        rows={1}
                        disabled={streaming}
                        className="textarea flex-1 min-h-[2.75rem] max-h-40"
                        style={{ resize: 'none', overflowY: 'auto', fieldSizing: 'content' }}
                    />

                    {streaming ? (
                        <button
                            onClick={stopGeneration}
                            className="btn-danger shrink-0 h-11 px-4"
                            title="Stop generation"
                        >
                            <Square size={14} fill="currentColor" />
                        </button>
                    ) : (
                        <button
                            onClick={sendMessage}
                            disabled={!input.trim() || !model}
                            className="btn-primary shrink-0 h-11 px-4"
                            title="Send (Enter)"
                        >
                            <Send size={14} />
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Message bubble — renders a single turn in the conversation
// ---------------------------------------------------------------------------

/**
 * @param {{ message: { role: string, content: string, streaming?: boolean, error?: string } }} props
 */
function MessageBubble({ message }) {
    const isUser = message.role === 'user';

    return (
        <div
            className={`flex gap-3 items-start animate-slide-up
                  ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
        >
            {/* Avatar */}
            <div
                className={[
                    'flex items-center justify-center w-8 h-8 rounded-full shrink-0 mt-0.5',
                    isUser
                        ? 'bg-accent/20 border border-accent/30'
                        : 'bg-surface-raised border border-white/10',
                ].join(' ')}
            >
                {isUser ? (
                    <User size={14} className="text-accent-light" />
                ) : (
                    <Bot size={14} className="text-txt-secondary" />
                )}
            </div>

            {/* Bubble */}
            <div
                className={[
                    'max-w-[78%] rounded-2xl px-4 py-3 relative',
                    isUser
                        ? // User: vibrant accent gradient, right-aligned
                        'bg-gradient-to-br from-accent to-accent-dark text-white rounded-tr-sm'
                        : // AI: dark card with subtle border, left-aligned
                        'bg-surface-card border border-white/[0.07] text-txt-primary rounded-tl-sm',
                ].join(' ')}
            >
                {/* Content */}
                {isUser ? (
                    // User messages: plain text, preserve newlines
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
                ) : (
                    // AI messages: full Markdown rendering
                    <div className={`markdown-body ${message.streaming ? 'streaming-cursor' : ''}`}>
                        {message.content ? (
                            <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={{
                                    /* Inline code */
                                    code({ node, inline, className, children, ...props }) {
                                        return inline ? (
                                            <code
                                                className="bg-surface-raised text-accent-light font-mono
                                   text-xs px-1.5 py-0.5 rounded"
                                                {...props}
                                            >
                                                {children}
                                            </code>
                                        ) : (
                                            <pre className="bg-surface-raised border border-white/10
                                      rounded-lg p-4 overflow-x-auto my-3">
                                                <code className="font-mono text-xs text-txt-primary" {...props}>
                                                    {children}
                                                </code>
                                            </pre>
                                        );
                                    },
                                }}
                            >
                                {message.content}
                            </ReactMarkdown>
                        ) : (
                            // Show only the cursor while content is empty (very start of stream)
                            !message.streaming && <span className="text-txt-muted text-xs">…</span>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// System error message — rendered for role === 'system-error'
// ---------------------------------------------------------------------------

/**
 * SystemErrorMessage — a full-width amber warning banner that renders
 * in place of the assistant bubble when the SSE stream delivers an error
 * event (e.g., when an embedding model is asked to chat).
 *
 * Visually distinct from MessageBubble so the user cannot mistake it for
 * a model response.
 *
 * @param {{ message: string }} props
 */
function SystemErrorMessage({ message }) {
    return (
        <div className="flex justify-center animate-slide-up w-full px-2">
            <div
                className={[
                    'flex items-start gap-3 w-full max-w-[90%]',
                    'bg-amber-500/10 border border-amber-500/25',
                    'rounded-xl px-4 py-3',
                ].join(' ')}
            >
                {/* Warning icon */}
                <div className="flex items-center justify-center w-7 h-7 rounded-lg
                                bg-amber-500/20 border border-amber-500/30 shrink-0 mt-0.5">
                    <AlertTriangle size={14} className="text-amber-400" />
                </div>

                {/* Text */}
                <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-amber-400 uppercase tracking-wide mb-0.5">
                        System Notice
                    </p>
                    <p className="text-sm text-amber-200/80 leading-relaxed">
                        {message}
                    </p>
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Consulting badge — rendered above the input bar during specialist delegation
// ---------------------------------------------------------------------------

/**
 * ConsultingBadge — animated indigo status pill displayed while the primary
 * model is internally consulting a specialist model.
 *
 * Visually distinct from SystemErrorMessage (amber) so users immediately
 * understand this is an informational progress indicator, not an error.
 *
 * @param {{ target: string }} props - target: the specialist model being queried
 */
function ConsultingBadge({ target }) {
    return (
        <div className="flex items-center justify-center mb-3 animate-slide-up">
            <div
                className={[
                    'inline-flex items-center gap-2',
                    'bg-indigo-500/15 border border-indigo-500/30',
                    'text-indigo-300 rounded-full px-4 py-1.5',
                ].join(' ')}
            >
                {/* Spinning indicator */}
                <Loader2 size={13} className="animate-spin text-indigo-400 shrink-0" />

                {/* Status text */}
                <span className="text-xs font-medium">
                    Consulting expert:&nbsp;
                    <span className="font-semibold text-indigo-200">{target}</span>
                    &nbsp;…
                </span>

                {/* Pulsing dot for extra visual emphasis */}
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse shrink-0" />
            </div>
        </div>
    );
}
