import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import InstalledList from './InstalledList';

describe('InstalledList', () => {
    it('renders empty state correctly', () => {
        render(<InstalledList models={[]} pullingName={null} onDelete={vi.fn()} onUpdate={vi.fn()} />);
        expect(screen.getByText('No models installed yet')).toBeInTheDocument();
        expect(screen.getByText('0 models on disk')).toBeInTheDocument();
    });

    it('renders models with their details', () => {
        const models = [
            { name: 'llama3', size: 4000000000, category: 'chat', details: { parameter_size: '8B', family: 'llama' } },
        ];
        render(<InstalledList models={models} pullingName={null} onDelete={vi.fn()} onUpdate={vi.fn()} />);

        expect(screen.getByText('llama3')).toBeInTheDocument();
        expect(screen.getByText('8B')).toBeInTheDocument();
        expect(screen.getByText('llama')).toBeInTheDocument();
        expect(screen.getByText(/1 model on disk/)).toBeInTheDocument();
    });

    it('triggers delete and update actions', () => {
        const onDelete = vi.fn();
        const onUpdate = vi.fn();
        const models = [{ name: 'phi3', size: 1000 }];

        render(<InstalledList models={models} pullingName={null} onDelete={onDelete} onUpdate={onUpdate} />);

        const delBtn = screen.getByTitle('Delete model');
        fireEvent.click(delBtn);
        expect(onDelete).toHaveBeenCalledWith('phi3');

        const updBtn = screen.getByTitle('Update model');
        fireEvent.click(updBtn);
        expect(onUpdate).toHaveBeenCalledWith('phi3');
    });

    it('disables buttons when pulling name matches', () => {
        const models = [{ name: 'phi3', size: 1000 }];
        render(<InstalledList models={models} pullingName="phi3" onDelete={vi.fn()} onUpdate={vi.fn()} />);

        expect(screen.getByTitle('Delete model')).toBeDisabled();
        expect(screen.getByTitle('Update model')).toBeDisabled();
        expect(screen.getByText('Updating…')).toBeInTheDocument();
    });
});
