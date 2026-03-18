import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ModelHub from './ModelHub';
import * as client from '../../api/client';

vi.mock('../../api/client', async (importOriginal) => {
    const actual = await importOriginal();
    return {
        ...actual,
        apiGet: vi.fn(),
        streamPost: vi.fn(),
        apiDelete: vi.fn(),
    };
});

describe('ModelHub', () => {
    it('fetches available models and renders children', async () => {
        client.apiGet.mockResolvedValue({ models: [{ name: 'llama3', description: 'test' }] });

        render(<ModelHub installedModels={[]} onModelsChange={vi.fn()} />);

        await waitFor(() => {
            expect(screen.getByText('Installed Models')).toBeInTheDocument();
            expect(screen.getByText('Available Models')).toBeInTheDocument();
        });
    });

    it('handles handleDelete success and failure silently', async () => {
        client.apiGet.mockResolvedValue({ models: [] });
        global.fetch = vi.fn().mockResolvedValueOnce({ ok: true });
        
        const onChange = vi.fn();
        render(<ModelHub installedModels={[{ name: 'llama3' }]} onModelsChange={onChange} />);

        await waitFor(() => screen.getAllByText('llama3'));

        // Click delete
        const delBtns = screen.getAllByRole('button', { name: /delete/i });
        fireEvent.click(delBtns[0]);

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledWith('/api/models/llama3', expect.objectContaining({ method: 'DELETE' }));
            expect(onChange).toHaveBeenCalled();
        });

        // Test failure path: shouldn't crash
        global.fetch.mockRejectedValueOnce(new Error('fail'));
        fireEvent.click(delBtns[0]);
        
        await waitFor(() => {
            expect(onChange).toHaveBeenCalledTimes(2); // still refreshes
        });
    });

    it('handles handleInstall with simulated stream', async () => {
        client.apiGet.mockResolvedValue({ models: [{ name: 'mistral' }] });
        
        let finishStream;
        client.streamPost.mockImplementation(async (url, body, onEvent) => {
            onEvent({ status: 'Downloading…', completed: 50, total: 100 });
            await new Promise(resolve => finishStream = resolve);
            onEvent({ status: 'Verifying…' }); // tests null progress fallback
        });

        const onChange = vi.fn();
        render(<ModelHub installedModels={[]} onModelsChange={onChange} />);

        await waitFor(() => screen.getAllByText('mistral'));
        const installBtns = screen.getAllByRole('button', { name: /install/i });
        
        fireEvent.click(installBtns[0]);

        // Banner should show up
        await waitFor(() => {
            expect(screen.getByText(/Downloading…/)).toBeInTheDocument();
            expect(screen.getByText('50%')).toBeInTheDocument();
        });

        finishStream();

        // Eventually finishes (since we didn't mock blocking behavior, the streamPost returns immediately)
        await waitFor(() => {
            expect(onChange).toHaveBeenCalled();
        });
    });

    it('handles handleInstall with stream error event', async () => {
        client.apiGet.mockResolvedValue({ models: [{ name: 'mistral' }] });
        
        let finishStream;
        // Simulates server returning an error event in the stream
        client.streamPost.mockImplementation(async (url, body, onEvent) => {
            onEvent({ error: 'Disk full' });
            await new Promise(resolve => finishStream = resolve);
        });

        render(<ModelHub installedModels={[]} onModelsChange={vi.fn()} />);
        await waitFor(() => screen.getAllByText('mistral'));
        
        fireEvent.click(screen.getAllByRole('button', { name: /install/i })[0]);

        await waitFor(() => {
            // Banner shows error
            expect(screen.getByText(/Error: Disk full/)).toBeInTheDocument();
        });
        
        finishStream();
        
        // Ensure the component finishes its cycle before test ends
        await waitFor(() => {
            expect(screen.queryByText(/Error: Disk full/)).not.toBeInTheDocument();
        });
    });

    it('handles handleInstall with rejected promise', async () => {
        client.apiGet.mockResolvedValue({ models: [{ name: 'mistral' }] });
        vi.useFakeTimers({ shouldAdvanceTime: true });
        
        client.streamPost.mockRejectedValue(new Error('Network error'));

        render(<ModelHub installedModels={[]} onModelsChange={vi.fn()} />);
        await waitFor(() => screen.getAllByText('mistral'));
        
        fireEvent.click(screen.getAllByRole('button', { name: /install/i })[0]);

        await waitFor(() => {
            // Banner shows Failed: Network error
            expect(screen.getByText(/Failed: Network error/)).toBeInTheDocument();
        });
        
        // Advance timers to clear the banner
        vi.runAllTimers();
        vi.useRealTimers();
    });

    it('handles handleUpdate via InstalledList', async () => {
        client.apiGet.mockResolvedValue({ models: [] });
        client.streamPost.mockResolvedValue({}); // instant resolve

        render(<ModelHub installedModels={[{ name: 'llama3' }]} onModelsChange={vi.fn()} />);
        await waitFor(() => screen.getAllByText('llama3'));

        // Update button
        fireEvent.click(screen.getByRole('button', { name: /update/i }));

        await waitFor(() => {
            // The 4th argument (AbortSignal) is not passed here, so we only expect 3 arguments.
            expect(client.streamPost).toHaveBeenCalledWith('/api/models/pull', { name: 'llama3' }, expect.any(Function));
        });
    });

    it('handles apiGet failure gracefully', async () => {
        client.apiGet.mockRejectedValue(new Error('offline'));
        render(<ModelHub installedModels={[]} onModelsChange={vi.fn()} />);
        
        // Just verify it doesn't crash and still renders structural elements
        await waitFor(() => {
            expect(screen.getByText('Installed Models')).toBeInTheDocument();
            expect(screen.getByText('Available Models')).toBeInTheDocument();
        });
    });
});
