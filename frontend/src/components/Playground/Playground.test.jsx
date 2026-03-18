import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import Playground from './Playground';

vi.mock('./AgentChat', () => ({
    default: ({ model }) => <div data-testid="mock-agent-chat">AgentChat: {model}</div>
}));

vi.mock('./RawConsole', () => ({
    default: ({ model }) => <div data-testid="mock-raw-console">RawConsole: {model}</div>
}));

vi.mock('./ModelSelector', () => ({
    default: ({ selected }) => <div data-testid="mock-model-selector">{selected}</div>
}));

describe('Playground', () => {
    it('shows empty state when no models are installed', () => {
        render(<Playground installedModels={[]} selectedModel="" onModelSelect={vi.fn()} />);
        expect(screen.getByText('No models installed')).toBeInTheDocument();
    });

    it('renders AgentChat by default when models exist', () => {
        render(
            <Playground
                installedModels={[{ name: 'llama3' }]}
                selectedModel="llama3"
                onModelSelect={vi.fn()}
            />
        );
        expect(screen.getByTestId('mock-agent-chat')).toHaveTextContent('AgentChat: llama3');
    });

    it('switches to Raw Console when toggle is clicked', async () => {
        const user = userEvent.setup();
        render(
            <Playground
                installedModels={[{ name: 'llama3' }]}
                selectedModel="llama3"
                onModelSelect={vi.fn()}
            />
        );

        const rawBtn = screen.getByRole('button', { name: /raw console/i });
        await user.click(rawBtn);

        expect(screen.getByTestId('mock-raw-console')).toHaveTextContent('RawConsole: llama3');
    });
});
