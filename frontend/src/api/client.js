/**
 * Central API client for the Ollama Dashboard.
 *
 * Key design decisions:
 *  - streamPost() uses fetch() + ReadableStream instead of EventSource because
 *    the native EventSource API only supports GET requests, while the backend's
 *    SSE endpoints (/api/chat, /api/raw, /api/models/pull) all require POST with
 *    a JSON body.
 *  - A TextDecoder runs in streaming mode (stream: true) so multi-byte UTF-8
 *    characters split across chunk boundaries are decoded correctly.
 *  - A line buffer accumulates partial lines between network packets. Only
 *    complete "data: …" lines are emitted to the caller callback.
 *  - The reader lock is always released in a finally block to prevent leaks.
 *  - An AbortController signal can be passed for cancellation (e.g. component
 *    unmount or "Stop" button).
 */

// Base URL is empty string; Vite's dev-server proxy forwards /api → :8000
const BASE = '';

// ---------------------------------------------------------------------------
// Standard JSON helpers
// ---------------------------------------------------------------------------

/**
 * Perform a GET request and parse the JSON response.
 *
 * @param {string} path - Relative URL, e.g. "/api/models"
 * @returns {Promise<any>} Parsed JSON body
 * @throws {Error} On non-2xx status
 */
export async function apiGet(path) {
    const res = await fetch(BASE + path);
    if (!res.ok) throw new Error(`GET ${path} → HTTP ${res.status}`);
    return res.json();
}

/**
 * Perform a DELETE request and parse the JSON response.
 *
 * @param {string} path - Relative URL, e.g. "/api/models/llama3:latest"
 * @returns {Promise<any>} Parsed JSON body
 * @throws {Error} On non-2xx status
 */
export async function apiDelete(path) {
    const res = await fetch(BASE + path, { method: 'DELETE' });
    if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `DELETE ${path} → HTTP ${res.status}`);
    }
    return res.json();
}

// ---------------------------------------------------------------------------
// Fetch-based SSE streaming
// ---------------------------------------------------------------------------

/**
 * POST JSON to an SSE endpoint and invoke a callback for each received event.
 *
 * Why not EventSource?
 * The W3C EventSource API only supports GET requests. Our streaming endpoints
 * need JSON bodies (model name, messages, prompt), so we implement the SSE
 * client-side protocol manually on top of fetch():
 *   1. Open a streaming fetch connection.
 *   2. Read raw bytes via response.body.getReader().
 *   3. Decode bytes to text with TextDecoder in streaming mode.
 *   4. Buffer incomplete lines across chunk boundaries.
 *   5. Parse complete "data: {json}" lines and call `onEvent`.
 *   6. Stop on "data: [DONE]" or when the stream closes.
 *
 * @param {string}        path     - Relative endpoint, e.g. "/api/chat"
 * @param {object}        body     - JSON-serialisable request payload
 * @param {function}      onEvent  - Called with each parsed event object
 * @param {AbortSignal}   [signal] - Optional AbortController.signal for cancellation
 * @returns {Promise<void>}
 * @throws {Error} On non-2xx HTTP response or unrecoverable network error
 */
export async function streamPost(path, body, onEvent, signal) {
    const response = await fetch(BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal,
    });

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const reader = response.body.getReader();

    // stream: true keeps the decoder's internal byte buffer alive between calls,
    // which is necessary to correctly decode multi-byte UTF-8 sequences that are
    // split across separate network packets.
    const decoder = new TextDecoder('utf-8', { fatal: false });

    // Accumulates characters from incomplete lines split across fetch chunks.
    let lineBuffer = '';

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            // Decode incoming bytes. The `stream: true` flag prevents the decoder
            // from flushing its internal buffer prematurely.
            lineBuffer += decoder.decode(value, { stream: true });

            // Split on LF. The last element may be an incomplete line so we hold
            // it in the buffer until the next chunk provides the rest.
            const lines = lineBuffer.split('\n');
            lineBuffer = lines.pop() ?? ''; // preserve the incomplete tail

            for (const line of lines) {
                // trimEnd() strips CR from CRLF line endings without touching leading space.
                const trimmed = line.trimEnd();

                if (!trimmed.startsWith('data: ')) continue;

                const payload = trimmed.slice(6); // remove the "data: " prefix

                // The server signals a clean end-of-stream with the [DONE] sentinel.
                if (payload === '[DONE]') return;

                try {
                    onEvent(JSON.parse(payload));
                } catch {
                    // Silently skip malformed JSON — the stream continues.
                }
            }
        }

        // Flush any bytes held by the TextDecoder's internal buffer after EOF.
        const tail = decoder.decode();
        if (tail.startsWith('data: ')) {
            const payload = tail.slice(6).trim();
            if (payload && payload !== '[DONE]') {
                try { onEvent(JSON.parse(payload)); } catch { /* ignore */ }
            }
        }
    } finally {
        // Always release the reader lock; prevents stream from being locked
        // when the component re-renders or unmounts mid-stream.
        reader.releaseLock();
    }
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

/**
 * Format a raw byte count into a human-readable string (GB, MB, KB, or B).
 *
 * @param {number} bytes
 * @returns {string}  e.g. "4.7 GB", "512 MB"
 */
export function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '—';
    if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
    if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`;
    if (bytes >= 1e3) return `${(bytes / 1e3).toFixed(0)} KB`;
    return `${bytes} B`;
}
