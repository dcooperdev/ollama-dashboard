import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import RawConsole from './RawConsole';
import * as client from '../../api/client';

vi.mock('../../api/client', async (importOriginal) => {
    const actual = await importOriginal();
    return {
        ...actual,
        streamPost: vi.fn(),
    };
});

describe('RawConsole', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('renders empty output initially', () => {
        render(<RawConsole model="llama3" />);
        expect(screen.getByRole('textbox')).toBeInTheDocument();
        expect(screen.getByText('Output will appear here…')).toBeInTheDocument();
    });

    it('streams response successfully', async () => {
        client.streamPost.mockImplementation(async (url, body, onEvent) => {
            onEvent({ token: 'Hello' });
            onEvent({ token: ' World' });
        });

        render(<RawConsole model="llama3" />);

        const input = screen.getByRole('textbox');
        fireEvent.change(input, { target: { value: 'Say hello' } });

        const runBtn = screen.getByRole('button', { name: /run prompt/i });
        fireEvent.click(runBtn);

        await waitFor(() => {
            expect(screen.getByText(/Hello World/)).toBeInTheDocument();
        });
        expect(client.streamPost).toHaveBeenCalledWith('/api/raw', { model: 'llama3', prompt: 'Say hello' }, expect.any(Function), expect.any(AbortSignal));
    });

    it('handles stream errors', async () => {
        client.streamPost.mockImplementation(async (url, body, onEvent) => {
            onEvent({ error: 'Model failed' });
        });

        render(<RawConsole model="llama3" />);

        fireEvent.change(screen.getByRole('textbox'), { target: { value: 'trigger error' } });
        fireEvent.click(screen.getByRole('button', { name: /run prompt/i }));

        await waitFor(() => {
            expect(screen.getByText(/Error: Model failed/)).toBeInTheDocument();
        });
    });

    it('handles connection reject', async () => {
        client.streamPost.mockRejectedValue(new Error('Network Down'));

        render(<RawConsole model="llama3" />);

        fireEvent.change(screen.getByRole('textbox'), { target: { value: 'trigger crash' } });
        fireEvent.click(screen.getByRole('button', { name: /run prompt/i }));

        await waitFor(() => {
            expect(screen.getByText(/Connection error: Network Down/)).toBeInTheDocument();
        });
    });

    it('stops generation', async () => {
        client.streamPost.mockImplementation((url, body, onEvent, signal) => {
            return new Promise((resolve, reject) => {
                if (signal) {
                    signal.addEventListener('abort', () => {
                        const err = new Error('Aborted');
                        err.name = 'AbortError';
                        reject(err);
                    });
                }
            });
        });
        render(<RawConsole model="llama3" />);
        fireEvent.change(screen.getByRole('textbox'), { target: { value: 'long prompt' } });
        fireEvent.click(screen.getByRole('button', { name: /run prompt/i }));

        const stopBtn = await screen.findByRole('button', { name: /stop/i });
        fireEvent.click(stopBtn);
        // Asserts state flips back
        await waitFor(() => {
            expect(screen.queryByRole('button', { name: /stop/i })).not.toBeInTheDocument();
        });
    });

    it('handles Ctrl+Enter shortcut', async () => {
        client.streamPost.mockResolvedValue();
        render(<RawConsole model="llama3" />);
        
        const input = screen.getByRole('textbox');
        fireEvent.change(input, { target: { value: 'Hello' } });
        fireEvent.keyDown(input, { key: 'Enter', ctrlKey: true });
        
        await waitFor(() => {
            expect(client.streamPost).toHaveBeenCalledWith('/api/raw', { model: 'llama3', prompt: 'Hello' }, expect.any(Function), expect.any(AbortSignal));
        });
    });

    it('handles clipboard copy and clear output', async () => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        Object.assign(navigator, {
            clipboard: { writeText: vi.fn().mockResolvedValue() }
        });

        client.streamPost.mockImplementation(async (url, body, onEvent) => {
            onEvent({ token: 'TestOutput' });
        });

        render(<RawConsole model="llama3" />);
        fireEvent.change(screen.getByRole('textbox'), { target: { value: 'hi' } });
        fireEvent.click(screen.getByRole('button', { name: /run prompt/i }));

        await waitFor(() => expect(screen.getByText(/TestOutput/)).toBeInTheDocument());

        // Click Copy
        const copyBtn = screen.getByRole('button', { name: /copy/i });
        fireEvent.click(copyBtn);

        await waitFor(() => {
            expect(navigator.clipboard.writeText).toHaveBeenCalledWith('TestOutput');
            expect(screen.getByText(/Copied!/)).toBeInTheDocument();
        });

        vi.runAllTimers();
        vi.useRealTimers();

        // Click Clear
        const clearBtn = screen.getByRole('button', { name: /clear/i });
        fireEvent.click(clearBtn);

        expect(screen.queryByText(/TestOutput/)).not.toBeInTheDocument();
    });

    it('shows streaming indicator while generating', async () => {
        // Mock streamPost to hang indefinitely so we can see the streaming state
        client.streamPost.mockImplementation((url, body, onEvent, signal) => new Promise(() => {}));

        render(<RawConsole model="llama3" />);
        fireEvent.change(screen.getByRole('textbox'), { target: { value: 'hi' } });
        fireEvent.click(screen.getByRole('button', { name: /run prompt/i }));

        await waitFor(() => {
            expect(screen.getByText(/● streaming/)).toBeInTheDocument();
        });
    });
});
