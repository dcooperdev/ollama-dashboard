import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ModelSelector from './ModelSelector';

describe('ModelSelector', () => {
    const models = [
        { name: 'llama3', details: { parameter_size: '8B' }, category: 'chat' },
        { name: 'mistral' }
    ];

    it('renders empty state when no models available', () => {
        render(<ModelSelector models={[]} selected="" onSelect={vi.fn()} />);
        expect(screen.getByText('No models installed')).toBeInTheDocument();
    });

    it('renders selected model details', () => {
        render(<ModelSelector models={models} selected="llama3" onSelect={vi.fn()} />);
        expect(screen.getByText('llama3')).toBeInTheDocument();
        expect(screen.getByText('8B')).toBeInTheDocument();
    });

    it('opens dropdown and allows selection', () => {
        const onSelect = vi.fn();
        render(<ModelSelector models={models} selected="llama3" onSelect={onSelect} />);

        const button = screen.getByRole('button');
        fireEvent.click(button);

        const option = screen.getByText('mistral');
        expect(option).toBeInTheDocument();
        fireEvent.click(option);

        expect(onSelect).toHaveBeenCalledWith('mistral');
    });

    it('closes when clicking outside', () => {
        render(<ModelSelector models={models} selected="llama3" onSelect={vi.fn()} />);
        const button = screen.getByRole('button');
        fireEvent.click(button);

        expect(screen.getByText('mistral')).toBeInTheDocument();

        fireEvent.mouseDown(document.body);

        expect(screen.queryByText('mistral')).not.toBeInTheDocument();
    });
});
