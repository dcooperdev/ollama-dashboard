import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from './App';
import * as client from './api/client';

vi.mock('./api/client', async (importOriginal) => {
    const actual = await importOriginal();
    return {
        ...actual,
        apiGet: vi.fn(),
        apiPost: vi.fn(),
        apiDelete: vi.fn(),
    };
});

describe('App', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        client.apiGet.mockImplementation((url) => {
            if (url === '/api/models') {
                return Promise.resolve({
                    models: [
                        { name: 'llama3:latest', details: { family: 'llama' } },
                    ],
                });
            }
            if (url === '/api/status') {
                return Promise.resolve({ internet: true, ollama: true });
            }
            return Promise.resolve({});
        });
    });

    it('renders sidebar and defaults to Model Hub', async () => {
        render(<App />);

        await waitFor(() => {
            // "1" will be found in the badge
            expect(screen.getByText('1')).toBeInTheDocument();
        });

        // The top header says Model Hub
        expect(screen.getByRole('heading', { name: /model hub/i })).toBeInTheDocument();
    });

    it('navigates to Playground when sidebar link is clicked', async () => {
        render(<App />);

        const playgroundBtn = screen.getByText('Playground', { selector: 'span' });
        fireEvent.click(playgroundBtn);

        expect(screen.getByRole('heading', { name: /playground/i })).toBeInTheDocument();
    });

    it('handles API error gracefully when loading models', async () => {
        client.apiGet.mockImplementation((url) => {
            if (url === '/api/status') return Promise.resolve({ internet: true, ollama: true });
            return Promise.reject(new Error('Connection refused'));
        });

        render(<App />);

        await waitFor(() => {
            expect(screen.getByText('0')).toBeInTheDocument();
        });
    });

    it('preserves selectedModel if already in list', async () => {
        // First load returns two models
        client.apiGet.mockImplementation((url) => {
            if (url === '/api/models') {
                return Promise.resolve({
                    models: [
                        { name: 'llama3:latest', details: { } },
                        { name: 'mistral:latest', details: { } }
                    ],
                });
            }
            if (url === '/api/status') return Promise.resolve({ internet: true, ollama: true });
            return Promise.resolve({});
        });

        render(<App />);

        // Wait for models to load
        await waitFor(() => {
            expect(screen.getByText('2')).toBeInTheDocument(); // 2 models on disk
        });

        // Navigate to Playground to see selected model
        fireEvent.click(screen.getByText('Playground', { selector: 'span' }));
        
        // In Playground, the ModelSelector should show 'llama3:latest' as selected
        expect(screen.getByText('llama3:latest', { selector: 'span.truncate' })).toBeInTheDocument();

        // Now simulate a delete which calls refreshModels
        // Since we are in Playground, we need to go back to Hub to click Delete
        fireEvent.click(screen.getByText('Model Hub', { selector: 'span' }));

        // Delete mistral:latest so llama3 remains
        client.apiDelete.mockResolvedValueOnce({});
        // apiGet will be called again by refreshModels, return only llama3
        client.apiGet.mockImplementation((url) => {
            if (url === '/api/models') {
                return Promise.resolve({
                    models: [
                        { name: 'llama3:latest', details: { } } // mistral is gone
                    ],
                });
            }
            return Promise.resolve({});
        });

        // Click delete on mistral
        const deleteBtns = screen.getAllByRole('button', { name: /delete/i });
        fireEvent.click(deleteBtns[1]); // second one is mistral

        // Wait for update
        await waitFor(() => {
            expect(screen.getByText('1')).toBeInTheDocument();
        });

        // Go back to Playground
        fireEvent.click(screen.getByText('Playground', { selector: 'span' }));

        // llama3:latest should still be selected
        expect(screen.getByText('llama3:latest', { selector: 'span.truncate' })).toBeInTheDocument();
    });
});
