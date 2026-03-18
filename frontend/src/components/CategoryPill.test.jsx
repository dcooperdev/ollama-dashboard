import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import CategoryPill from './CategoryPill';

describe('CategoryPill', () => {
    it('renders the default chat category', () => {
        render(<CategoryPill />);
        const element = screen.getByText('chat');
        expect(element).toBeInTheDocument();
        expect(element).toHaveClass('uppercase');
        expect(element).toHaveClass('bg-emerald-500/15'); // default style
    });

    it('renders a custom category', () => {
        render(<CategoryPill category="vision" className="ml-2" />);
        const element = screen.getByText('vision');
        expect(element).toBeInTheDocument();
        expect(element).toHaveClass('bg-purple-500/15');
        expect(element).toHaveClass('ml-2');
    });

    it('falls back to chat styles for unknown categories', () => {
        render(<CategoryPill category="unknown_weird" />);
        const element = screen.getByText('unknown_weird');
        expect(element).toBeInTheDocument();
        expect(element).toHaveClass('bg-emerald-500/15');
    });
});
