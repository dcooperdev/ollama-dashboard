import { useState, useRef, useEffect } from 'react';
import { Play, Square, Trash2, Copy, Check, Terminal } from 'lucide-react';
import { streamPost } from '../../api/client.js';

/**
 * RawConsole — a terminal-style interface for raw prompt → completion
 * without any chat history or message formatting.
 *
 * Designed for:
 *  - Testing system prompts in isolation.
 *  - Inspecting raw model output without markdown rendering.
 *  - Debugging tokenisation and format compliance.
 *
 * Implementation notes:
 *  - Uses the same fetch + ReadableStream SSE pattern as AgentChat.
 *  - An AbortController is used both for the Stop button and for cleanup
 *    on component unmount.
 *  - Output is rendered in a monospace pre element so whitespace, indentation,
 *    and ANSI-like escape sequences are preserved exactly as-is.
 *
 * @param {{ model: string }} props
 */
export default function RawConsole({ model }) {
    const [prompt, setPrompt] = useState('');
    const [output, setOutput] = useState('');
    const [streaming, setStreaming] = useState(false);
    const [copied, setCopied] = useState(false);

    const abortRef = useRef(null);
    const outputRef = useRef(null);

    // Cancel any running stream on unmount.
    useEffect(() => {
        return () => abortRef.current?.abort();
    }, []);

    // Auto-scroll the output panel as tokens arrive.
    useEffect(() => {
        if (outputRef.current) {
            outputRef.current.scrollTop = outputRef.current.scrollHeight;
        }
    }, [output]);

    /** Send the prompt and stream the response. */
    const runPrompt = async () => {
        if (!prompt.trim() || streaming || !model) return;

        setOutput('');
        setStreaming(true);
        abortRef.current = new AbortController();

        try {
            await streamPost(
                '/api/raw',
                { model, prompt: prompt.trim() },
                (event) => {
                    if (event.token) {
                        setOutput((prev) => prev + event.token);
                    }
                    if (event.error) {
                        setOutput((prev) => prev + `\n[Error: ${event.error}]`);
                    }
                },
                abortRef.current.signal,
            );
        } catch (err) {
            if (err.name !== 'AbortError') {
                setOutput((prev) => prev + `\n[Connection error: ${err.message}]`);
            }
        } finally {
            setStreaming(false);
        }
    };

    /** Stop the current generation. */
    const stopGeneration = () => abortRef.current?.abort();

    /** Copy output to the clipboard. */
    const copyOutput = async () => {
        if (!output) return;
        try {
            await navigator.clipboard.writeText(output);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // Clipboard API may be blocked in some environments.
        }
    };

    /** Submit on Ctrl+Enter or Cmd+Enter. */
    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            runPrompt();
        }
    };

    return (
        <div className="flex flex-col h-full min-h-0 p-6 gap-4">
            {/* ---- Prompt section ---- */}
            <div className="card p-4 flex flex-col gap-3 shrink-0">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs text-txt-secondary">
                        <Terminal size={13} className="text-accent" />
                        <span className="font-mono">{model}</span>
                        <span className="text-txt-muted">/ prompt</span>
                    </div>
                    <span className="text-[10px] text-txt-muted">
                        Ctrl+Enter to run
                    </span>
                </div>

                <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Enter your raw prompt here…"
                    rows={5}
                    disabled={streaming}
                    className="textarea font-mono text-xs leading-relaxed"
                />

                <div className="flex gap-2">
                    {streaming ? (
                        <button onClick={stopGeneration} className="btn-danger">
                            <Square size={13} fill="currentColor" />
                            Stop
                        </button>
                    ) : (
                        <button
                            onClick={runPrompt}
                            disabled={!prompt.trim() || !model}
                            className="btn-primary"
                        >
                            <Play size={13} fill="currentColor" />
                            Run Prompt
                        </button>
                    )}

                    {output && !streaming && (
                        <button onClick={() => setOutput('')} className="btn-ghost">
                            <Trash2 size={13} />
                            Clear
                        </button>
                    )}
                </div>
            </div>

            {/* ---- Output section ---- */}
            <div className="card flex flex-col flex-1 min-h-0">
                {/* Output header */}
                <div
                    className="flex items-center justify-between px-4 py-2.5
                        border-b border-white/[0.05] shrink-0"
                >
                    <div className="flex items-center gap-2 text-xs text-txt-secondary">
                        <Terminal size={12} className="text-txt-muted" />
                        <span>Output</span>
                        {streaming && (
                            <span className="text-[10px] text-status-warning font-mono animate-pulse-dot">
                                ● streaming
                            </span>
                        )}
                    </div>

                    {output && (
                        <button onClick={copyOutput} className="btn-ghost text-xs py-1">
                            {copied ? (
                                <>
                                    <Check size={12} className="text-status-online" />
                                    Copied!
                                </>
                            ) : (
                                <>
                                    <Copy size={12} />
                                    Copy
                                </>
                            )}
                        </button>
                    )}
                </div>

                {/* Monospace output window */}
                <div
                    ref={outputRef}
                    className="flex-1 overflow-y-auto px-4 py-4 min-h-0"
                >
                    {!output && !streaming ? (
                        <p className="text-xs text-txt-muted font-mono italic">
                            Output will appear here…
                        </p>
                    ) : (
                        <pre
                            className={[
                                'font-mono text-xs text-txt-primary whitespace-pre-wrap',
                                'leading-relaxed break-words',
                                streaming ? 'streaming-cursor' : '',
                            ].join(' ')}
                        >
                            {output}
                        </pre>
                    )}
                </div>
            </div>
        </div>
    );
}
