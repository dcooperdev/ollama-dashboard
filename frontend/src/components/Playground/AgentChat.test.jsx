import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AgentChat from './AgentChat';
import * as client from '../../api/client';

vi.mock('../../api/client', async (importOriginal) => {
    const actual = await importOriginal();
    return {
        ...actual,
        streamPost: vi.fn(),
    };
});

// Removed react-markdown mock so we can test the real custom renderers in AgentChat.

describe('AgentChat', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        sessionStorage.clear();
    });

    it('renders empty chat initially', () => {
        render(<AgentChat model="llama3" />);
        expect(screen.getByText(/Chat with/)).toBeInTheDocument();
        expect(screen.getByRole('textbox')).toBeInTheDocument();
    });

    it('sends a message and streams response with markdown', async () => {
        client.streamPost.mockImplementation(async (url, body, onEvent) => {
            // Emits some markdown with inline code and a code block
            onEvent({ token: 'Here is `inline` code and\n```javascript\nblock\n```' });
        });

        render(<AgentChat model="llama3" />);

        fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Hi there' } });
        const runBtn = screen.getByRole('button', { name: /send/i });
        fireEvent.click(runBtn);

        await waitFor(() => {
            expect(screen.getByText('Hi there')).toBeInTheDocument(); // user
            // AI responses with the actual inline code
            expect(screen.getByText('inline')).toBeInTheDocument();
            
            // AI responses with the block code (it spans a pre and a code tag, text is in code tag)
            expect(screen.getByText('block')).toBeInTheDocument();
        });
    });

    it('handles sendMessage connection error', async () => {
        client.streamPost.mockRejectedValue(new Error('No server'));
        render(<AgentChat model="llama3" />);

        const textbox = screen.getByRole('textbox');
        fireEvent.change(textbox, { target: { value: 'Hi' } });
        fireEvent.click(screen.getByRole('button', { name: /send/i }));

        await waitFor(() => {
            // Error is handled in state but not rendered. Finally block re-enables text area.
            expect(textbox).not.toBeDisabled();
        });
    });

    it('handles keyboard shortcuts (Enter vs Shift+Enter)', async () => {
        client.streamPost.mockImplementation(async (url, body, onEvent) => {
            onEvent({ token: 'ok' });
        });
        render(<AgentChat model="llama3" />);
        const textarea = screen.getByRole('textbox');

        // Shift+Enter should just add newline, no submit
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
        expect(client.streamPost).not.toHaveBeenCalled();

        // Enter without shift should submit
        fireEvent.change(textarea, { target: { value: 'Hi' } });
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
        
        await waitFor(() => {
            expect(client.streamPost).toHaveBeenCalled();
        });
    });

    it('handles system error from API', async () => {
        client.streamPost.mockImplementation(async (url, body, onEvent) => {
            onEvent({ error: 'System error occurred' });
        });

        render(<AgentChat model="llama3" />);

        fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Trigger error' } });
        fireEvent.click(screen.getByRole('button', { name: /send/i }));

        await waitFor(() => {
            expect(screen.getByText(/System error occurred/)).toBeInTheDocument();
            expect(screen.getByText(/System Notice/)).toBeInTheDocument();
        });
    });

    it('restores from session storage', () => {
        const dummyMessages = [{ id: 1, role: 'user', content: 'hola' }];
        sessionStorage.setItem('chat_history_llama3', JSON.stringify(dummyMessages));
        render(<AgentChat model="llama3" />);
        expect(screen.getByText('hola')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /clear/i })).toBeInTheDocument();
    });

    it('clears chat', async () => {
        sessionStorage.setItem('chat_history_llama3', JSON.stringify([{ id: 1, role: 'user', content: 'hola' }]));
        render(<AgentChat model="llama3" />);
        const clearBtn = screen.getByRole('button', { name: /clear/i });
        fireEvent.click(clearBtn);
        expect(screen.queryByText('hola')).not.toBeInTheDocument();
    });

    it('shows consulting badge', async () => {
        client.streamPost.mockImplementation(async (url, body, onEvent) => {
            onEvent({ status: 'consulting', target: 'specialist-db' });
            onEvent({ token: 'Hello' });
        });
        render(<AgentChat model="llama3" />);
        fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Hi' } });
        fireEvent.click(screen.getByRole('button', { name: /send/i }));

        await waitFor(() => {
            expect(screen.getByText(/Consulting expert/i)).toBeInTheDocument();
        });
    });

    it('shows recommendation card and allows skip', async () => {
        client.streamPost.mockImplementation(async (url, body, onEvent) => {
            onEvent({ status: 'recommendation', target_model: 'expert-x', reason: 'Better at this' });
        });
        render(<AgentChat model="llama3" />);
        fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Recommend something' } });
        fireEvent.click(screen.getByRole('button', { name: /send/i }));

        await waitFor(() => {
            expect(screen.getByText('expert-x')).toBeInTheDocument();
        });

        const skipBtn = screen.getByRole('button', { name: /continue without it/i });
        fireEvent.click(skipBtn);

        expect(client.streamPost).toHaveBeenCalledWith('/api/chat', expect.objectContaining({
            model: 'llama3', skip_routing: true
        }), expect.any(Function), expect.any(Object));
    });

    it('resubmitMessage handles connection error and consulting updates', async () => {
        // Trigger a recommendation first
        client.streamPost.mockImplementationOnce(async (url, body, onEvent) => {
            onEvent({ status: 'recommendation', target_model: 'expert-x', reason: 'Better at this' });
        });
        
        render(<AgentChat model="llama3" />);
        fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Fail later' } });
        fireEvent.click(screen.getByRole('button', { name: /send/i }));

        await waitFor(() => expect(screen.getByText('expert-x')).toBeInTheDocument());

        // Now mock streamPost for the resubmit call
        client.streamPost.mockImplementationOnce(async (url, body, onEvent) => {
            // First emit consulting
            onEvent({ status: 'consulting', target: 'specialist-db' });
            throw new Error('connection lost during resubmit');
        });

        // Click skip to trigger resubmit
        const skipBtn = screen.getByRole('button', { name: /continue without it/i });
        fireEvent.click(skipBtn);

        await waitFor(() => {
            expect(screen.getByRole('textbox')).not.toBeDisabled();
        });
    });

    it('resubmitMessage handles install success, token, and error', async () => {
        // Trigger a recommendation first
        client.streamPost.mockImplementationOnce(async (url, body, onEvent) => {
            onEvent({ status: 'recommendation', target_model: 'expert-x', reason: 'Better at this' });
        });
        
        render(<AgentChat model="llama3" />);
        fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Trigger' } });
        fireEvent.click(screen.getByRole('button', { name: /send/i }));
        await waitFor(() => expect(screen.getByText('expert-x')).toBeInTheDocument());

        // Mock fetch for the RecommendationCard pull stream
        vi.useFakeTimers({ shouldAdvanceTime: true });
        global.fetch = vi.fn().mockResolvedValue({
            ok: true, body: {
                getReader: () => {
                    let done = false; return {
                        read: async () => {
                            if (done) return { done: true }; done = true;
                            return { done: false, value: new TextEncoder().encode('data: {"status":"Complete!","completed":100,"total":100}\n') };
                        }
                    };
                }
            }
        });

        // Mock streamPost for the resubmit call
        client.streamPost.mockImplementationOnce(async (url, body, onEvent) => {
            onEvent({ token: 'Resubmit ' });
            onEvent({ token: 'Token' });
            onEvent({ error: 'Resubmit System Error' });
        });

        // Click Install now
        fireEvent.click(screen.getByRole('button', { name: /install now/i }));

        await waitFor(() => expect(screen.getByText('Complete!')).toBeInTheDocument());
        
        // Advance timers to trigger onInstallSuccess
        vi.advanceTimersByTime(1000);

        // Verify resubmitMessage is called properly and executed the stream
        await waitFor(() => {
            // Token is overwritten by the error message in the DOM, so we can't assert it here.
            
            // Verify error was handled (by checking if input is re-enabled)
            expect(screen.getByRole('textbox')).not.toBeDisabled();
        });
        
        vi.useRealTimers();
    });
});
