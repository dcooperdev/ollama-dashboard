import { useState } from 'react';
import { MessageSquare, Terminal } from 'lucide-react';
import ModelSelector from './ModelSelector.jsx';
import AgentChat from './AgentChat.jsx';
import RawConsole from './RawConsole.jsx';

/**
 * Playground — mode switcher between Agent Chat and Raw Console.
 *
 * Renders the model selector and a mode toggle at the top, then
 * delegates all rendering to AgentChat or RawConsole below.
 *
 * @param {{
 *   installedModels: Array,
 *   selectedModel: string,
 *   onModelSelect: function,
 * }} props
 */
export default function Playground({ installedModels, selectedModel, onModelSelect }) {
    const [mode, setMode] = useState('chat'); // 'chat' | 'raw'

    const modes = [
        { id: 'chat', label: 'Agent Chat', icon: MessageSquare },
        { id: 'raw', label: 'Raw Console', icon: Terminal },
    ];

    const hasModels = installedModels.length > 0;

    return (
        <div className="h-full flex flex-col">
            {/* Control bar */}
            <div
                className="flex items-center gap-4 px-6 py-3 border-b border-white/[0.05]
                      bg-surface-base/30 shrink-0"
            >
                {/* Model selector */}
                <ModelSelector
                    models={installedModels}
                    selected={selectedModel}
                    onSelect={onModelSelect}
                />

                {/* Mode toggle */}
                <div className="flex items-center gap-1 bg-surface-raised rounded-lg p-1 ml-auto">
                    {modes.map(({ id, label, icon: Icon }) => (
                        <button
                            key={id}
                            onClick={() => setMode(id)}
                            className={[
                                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium',
                                'transition-all duration-150',
                                mode === id
                                    ? 'bg-accent text-white shadow-accent/20'
                                    : 'text-txt-secondary hover:text-txt-primary hover:bg-white/5',
                            ].join(' ')}
                        >
                            <Icon size={13} />
                            {label}
                        </button>
                    ))}
                </div>
            </div>

            {/* No models installed? Show an actionable empty state. */}
            {!hasModels ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
                    <Terminal size={40} className="text-txt-muted mb-4 opacity-40" />
                    <p className="text-sm font-semibold text-txt-secondary">No models installed</p>
                    <p className="text-xs text-txt-muted mt-1">
                        Go to the <span className="text-accent-light">Model Hub</span> to install a model first.
                    </p>
                </div>
            ) : mode === 'chat' ? (
                <AgentChat key={selectedModel} model={selectedModel} />
            ) : (
                <RawConsole key={selectedModel} model={selectedModel} />
            )}
        </div>
    );
}
