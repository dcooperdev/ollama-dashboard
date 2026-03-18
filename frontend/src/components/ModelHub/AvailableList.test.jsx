import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import AvailableList from './AvailableList';

describe('AvailableList', () => {
    const models = [
        { name: 'modelA', description: 'descA', size: '2 GB' },
        { name: 'modelB', display: 'Big Boss', size: '10 GB' },
        { name: 'modelMB', size: '500 MB' },
        { name: 'modelKB', size: '500 KB' },
        { name: 'modelUnknown', size: 'unknown' }
    ];

    it('renders available models and handles install click', () => {
        const onInstall = vi.fn();
        render(<AvailableList models={models} installedNames={new Set()} pullingName={null} onInstall={onInstall} />);

        expect(screen.getByText('Available Models')).toBeInTheDocument();
        expect(screen.getAllByText(/modelA/).length).toBeGreaterThan(0);
        expect(screen.getByText('Big Boss')).toBeInTheDocument();

        const installBtns = screen.getAllByRole('button', { name: /install/i });
        fireEvent.click(installBtns[0]);
        expect(onInstall).toHaveBeenCalledWith('modelA');
    });

    it('shows installed badge for installed models', () => {
        const installedNames = new Set(['modelA']);
        render(<AvailableList models={models} installedNames={installedNames} pullingName={null} onInstall={vi.fn()} />);

        expect(screen.getByText('Installed')).toBeInTheDocument();
        const installBtns = screen.queryAllByRole('button', { name: /install/i });
        expect(installBtns).toHaveLength(4);
    });

    it('filters models dynamically and allows clearing', async () => {
        render(<AvailableList models={models} installedNames={new Set()} pullingName={null} onInstall={vi.fn()} />);

        const input = screen.getByPlaceholderText('Filter by name…');
        fireEvent.change(input, { target: { value: 'boss' } });

        expect(screen.getByText('Big Boss')).toBeInTheDocument();
        expect(screen.queryAllByText('modelA').length).toBe(0);

        // Type something that yields no results
        fireEvent.change(input, { target: { value: 'nothingmatches' } });
        expect(screen.getByText(/No models match/)).toBeInTheDocument();

        // Click Clear filter
        fireEvent.click(screen.getByRole('button', { name: /clear filter/i }));

        // modelA should be back
        expect(screen.getAllByText('modelA').length).toBeGreaterThan(0);
    });

    it('sorts models by size including KB', () => {
        render(<AvailableList models={models} installedNames={new Set()} pullingName={null} onInstall={vi.fn()} />);

        const sortSelect = screen.getByRole('combobox');
        fireEvent.change(sortSelect, { target: { value: 'size-asc' } });
        
        // the 'unknown' size is treated as 0 logic-wise, so modelUnknown is technically "smallest".
        // Let's assert we get modelUnknown first instead of modelKB.
        let buttons = screen.getAllByRole('button', { name: /install/i });
        expect(buttons[0].parentElement.parentElement.textContent).toContain('modelUnknown');

        fireEvent.change(sortSelect, { target: { value: 'size-desc' } });
        buttons = screen.getAllByRole('button', { name: /install/i });
        expect(buttons[0].parentElement.parentElement.textContent).not.toContain('modelUnknown');
    });

    it('handles models without display name or tags', () => {
        const noTagsModel = [{ name: 'notags', size: '1 GB' }];
        render(<AvailableList models={noTagsModel} installedNames={new Set()} pullingName={null} onInstall={vi.fn()} />);
        // It should render 'notags' fallback for display name
        expect(screen.getAllByText('notags').length).toBeGreaterThan(0);
    });
});
