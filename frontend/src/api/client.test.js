import { apiGet, apiDelete, formatBytes, streamPost } from './client';

global.fetch = vi.fn();

describe('api client', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('apiGet', () => {
        it('fetches JSON successfully', async () => {
            fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => ({ status: 'ok' })
            });

            const result = await apiGet('/test');
            expect(fetch).toHaveBeenCalledWith('/test');
            expect(result).toEqual({ status: 'ok' });
        });

        it('throws an error if response is not ok', async () => {
            fetch.mockResolvedValueOnce({
                ok: false,
                status: 500
            });

            await expect(apiGet('/test')).rejects.toThrow('GET /test → HTTP 500');
        });
    });

    describe('apiDelete', () => {
        it('deletes successfully and parses JSON', async () => {
            fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => ({ success: true })
            });

            const result = await apiDelete('/del');
            expect(fetch).toHaveBeenCalledWith('/del', { method: 'DELETE' });
            expect(result).toEqual({ success: true });
        });

        it('throws an error with message if delete fails', async () => {
            fetch.mockResolvedValueOnce({
                ok: false,
                status: 404,
                text: async () => 'Not found'
            });

            await expect(apiDelete('/del')).rejects.toThrow('Not found');
        });
    });

    describe('formatBytes', () => {
        it('formats B, KB, MB, GB correctly', () => {
            expect(formatBytes(0)).toBe('—');
            expect(formatBytes(null)).toBe('—');
            expect(formatBytes(500)).toBe('500 B');
            expect(formatBytes(2500)).toBe('3 KB');
            expect(formatBytes(1500000)).toBe('2 MB');
            expect(formatBytes(2500000000)).toBe('2.5 GB');
        });
    });

    it('streamPost handles streaming response', async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            body: {
                getReader: () => {
                    let done = false;
                    return {
                        read: async () => {
                            if (done) return { done: true };
                            done = true;
                            return { done: false, value: new TextEncoder().encode('data: {"token":"t1"}\n\ndata: {"token":"t2"}\n\n') };
                        },
                        releaseLock: vi.fn()
                    };
                }
            }
        });

        const onEvent = vi.fn();
        await streamPost('/api/stream', { model: 'm1' }, onEvent);
        expect(onEvent).toHaveBeenCalledWith({ token: 't1' });
        expect(onEvent).toHaveBeenCalledWith({ token: 't2' });
    });

    it('streamPost throws on non-ok response', async () => {
        global.fetch.mockResolvedValueOnce({
            ok: false,
            status: 403,
            text: async () => 'Forbidden'
        });
        await expect(streamPost('/api/stream', {}, vi.fn())).rejects.toThrow('HTTP 403: Forbidden');
    });

    it('streamPost handles [DONE] sentinel cleanly', async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            body: {
                getReader: () => {
                    let doneStr = false;
                    return {
                        read: async () => {
                            if (doneStr) return { done: true };
                            doneStr = true;
                            // Send some data then [DONE]
                            return { done: false, value: new TextEncoder().encode('data: {"token":"t1"}\n\ndata: [DONE]\n\n') };
                        },
                        releaseLock: vi.fn()
                    };
                }
            }
        });

        const onEvent = vi.fn();
        await streamPost('/api/stream', {}, onEvent);
        expect(onEvent).toHaveBeenCalledTimes(1);
        expect(onEvent).toHaveBeenCalledWith({ token: 't1' });
    });

    it('streamPost flushes tail bytes', async () => {
        // We mock TextDecoder to simulate the rare case where decode() on EOF 
        // yields a remainder string starting with 'data: '
        const OriginalDecoder = global.TextDecoder;
        try {
            global.TextDecoder = vi.fn().mockImplementation(function () {
                return {
                    decode: (val, options) => {
                        if (!options?.stream) {
                            return 'data: {"token":"tail"}'; // final flush
                        }
                        return ''; // normal stream read returns empty
                    }
                };
            });

            global.fetch.mockResolvedValueOnce({
                ok: true,
                body: {
                    getReader: () => {
                        let doneStr = false;
                        return {
                            read: async () => {
                                if (doneStr) return { done: true };
                                doneStr = true;
                                // Give some arbitrary bytes
                                return { done: false, value: new Uint8Array([1,2,3]) };
                            },
                            releaseLock: vi.fn()
                        };
                    }
                }
            });

            const onEvent = vi.fn();
            await streamPost('/api/stream', {}, onEvent);
            expect(onEvent).toHaveBeenCalledTimes(1);
            expect(onEvent).toHaveBeenCalledWith({ token: 'tail' });
        } finally {
            global.TextDecoder = OriginalDecoder;
        }
    });


    it('apiDelete handles successful deletes', async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ status: 'deleted' })
        });
        const res = await apiDelete('/api/test-del');
        expect(res.status).toBe('deleted');
        expect(global.fetch).toHaveBeenCalledWith('/api/test-del', { method: 'DELETE' });
    });

    it('apiDelete handles error deletes', async () => {
        global.fetch.mockResolvedValueOnce({
            ok: false,
            status: 404,
            text: async () => 'Not Found'
        });
        await expect(apiDelete('/api/test-del')).rejects.toThrow('Not Found');
    });
});
