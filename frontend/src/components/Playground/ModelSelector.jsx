import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Cpu } from 'lucide-react';
import CategoryPill from '../CategoryPill.jsx';

/**
 * ModelSelector — a custom dropdown to choose the active model for the session.
 *
 * Renders a button that shows the currently selected model name with the
 * parameter_size detail (if available), and expands a floating list of
 * all installed models on click. Closes on outside-click.
 *
 * @param {{
 *   models: Array<{ name: string, details?: { parameter_size: string } }>,
 *   selected: string,
 *   onSelect: function,
 * }} props
 */
export default function ModelSelector({ models, selected, onSelect }) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);

    // Close the dropdown when the user clicks outside of it.
    useEffect(() => {
        const handler = (e) => {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    // Derive display info for the selected model.
    const selectedInfo = models.find((m) => m.name === selected);
    const params = selectedInfo?.details?.parameter_size;

    if (models.length === 0) {
        return (
            <div className="flex items-center gap-2 text-xs text-txt-muted px-3 py-2
                      bg-surface-raised rounded-lg border border-white/10">
                <Cpu size={14} />
                No models installed
            </div>
        );
    }

    return (
        <div ref={ref} className="relative">
            {/* Trigger button */}
            <button
                onClick={() => setOpen((o) => !o)}
                className="flex items-center gap-2.5 min-w-[220px]
                   bg-surface-raised border border-white/10
                   hover:border-accent/40 text-sm text-txt-primary
                   px-3 py-2 rounded-lg transition-all duration-150
                   focus:outline-none focus:border-accent/60"
            >
                <Cpu size={14} className="text-accent shrink-0" />
                <span className="flex-1 text-left truncate">
                    {selected || 'Select a model'}
                </span>
                {selectedInfo?.category && (
                    <CategoryPill category={selectedInfo.category} className="shrink-0" />
                )}
                {params && (
                    <span className="text-[10px] font-mono text-txt-muted shrink-0">
                        {params}
                    </span>
                )}
                <ChevronDown
                    size={14}
                    className={`text-txt-muted transition-transform duration-200 shrink-0
                      ${open ? 'rotate-180' : ''}`}
                />
            </button>

            {/* Dropdown list */}
            {open && (
                <div
                    className="absolute top-full left-0 mt-2 w-full min-w-[260px] z-50
                     bg-surface-raised border border-white/10 rounded-xl
                     shadow-card overflow-hidden animate-slide-up"
                >
                    {models.map((model) => {
                        const isSelected = model.name === selected;
                        const p = model.details?.parameter_size;
                        return (
                            <button
                                key={model.name}
                                onClick={() => {
                                    onSelect(model.name);
                                    setOpen(false);
                                }}
                                className={[
                                    'flex items-center justify-between w-full px-3 py-2.5',
                                    'text-sm transition-colors duration-100 text-left',
                                    isSelected
                                        ? 'bg-accent/15 text-white'
                                        : 'text-txt-secondary hover:bg-white/5 hover:text-txt-primary',
                                ].join(' ')}
                            >
                                <span className="truncate">{model.name}</span>
                                <div className="flex items-center gap-1.5 ml-2 shrink-0">
                                    {model.category && <CategoryPill category={model.category} />}
                                    {p && (
                                        <span className="text-[10px] font-mono text-txt-muted">
                                            {p}
                                        </span>
                                    )}
                                </div>
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
