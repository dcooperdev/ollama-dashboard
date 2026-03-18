import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import StatusBar from './StatusBar';
import * as client from '../api/client';

vi.mock('../api/client', async (importOriginal) => {
    const actual = await importOriginal();
    return {
        ...actual,
        apiGet: vi.fn(),
    };
});

describe('StatusBar', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('displays loading state initially', () => {
        client.apiGet.mockImplementation(() => new Promise(() => { }));
        const { container } = render(<StatusBar />);
        expect(container.querySelectorAll('.animate-pulse-dot')).toHaveLength(2);
        expect(screen.getByText('Internet')).toBeInTheDocument();
        expect(screen.getByText('Ollama')).toBeInTheDocument();
    });

    it('updates status when API returns true', async () => {
        client.apiGet.mockResolvedValue({ internet: true, ollama: true });
        render(<StatusBar />);

        await waitFor(() => {
            const onlinePills = document.querySelectorAll('.pill-online');
            expect(onlinePills).toHaveLength(2);
        });
    });

    it('shows offline status when API throws', async () => {
        client.apiGet.mockRejectedValue(new Error('Network error'));
        render(<StatusBar />);

        await waitFor(() => {
            const offlinePills = document.querySelectorAll('.pill-offline');
            expect(offlinePills).toHaveLength(2);
        });
    });
});
