import { Trash2, RefreshCw, HardDrive, Layers } from 'lucide-react';
import { formatBytes } from '../../api/client.js';
import CategoryPill from '../CategoryPill.jsx';

/**
 * InstalledList — renders the locally installed Ollama models.
 *
 * Each model card shows the name, parameter size, disk size, and provides
 * Delete and Update action buttons.
 *
 * @param {{
 *   models: Array,
 *   pullingName: string|null,
 *   onDelete: function,
 *   onUpdate: function,
 * }} props
 */
export default function InstalledList({ models, pullingName, onDelete, onUpdate }) {
    return (
        <section className="flex flex-col flex-[3] min-w-0">
            {/* Section header */}
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h2 className="text-base font-semibold text-white">Installed Models</h2>
                    <p className="text-xs text-txt-secondary mt-0.5">
                        {models.length} model{models.length !== 1 ? 's' : ''} on disk
                    </p>
                </div>
            </div>

            {/* Empty state */}
            {models.length === 0 && (
                <div className="card flex flex-col items-center justify-center py-16 text-center">
                    <HardDrive size={36} className="text-txt-muted mb-3 opacity-50" />
                    <p className="text-sm font-medium text-txt-secondary">No models installed yet</p>
                    <p className="text-xs text-txt-muted mt-1">
                        Browse the catalogue on the right to install your first model.
                    </p>
                </div>
            )}

            {/* Model cards */}
            <div className="flex flex-col gap-3 overflow-y-auto pr-1">
                {models.map((model) => (
                    <ModelCard
                        key={model.name}
                        model={model}
                        isUpdating={pullingName === model.name}
                        onDelete={onDelete}
                        onUpdate={onUpdate}
                    />
                ))}
            </div>
        </section>
    );
}

/**
 * Individual installed model card.
 *
 * @param {{ model: object, isUpdating: boolean, onDelete: function, onUpdate: function }} props
 */
function ModelCard({ model, isUpdating, onDelete, onUpdate }) {
    const params = model.details?.parameter_size;
    const family = model.details?.family;

    return (
        <div
            className="card p-4 flex items-center gap-4
                 transition-all duration-200 hover:border-white/10
                 animate-slide-up"
        >
            {/* Icon */}
            <div
                className="flex items-center justify-center w-10 h-10 rounded-lg
                      bg-accent/10 border border-accent/20 shrink-0"
            >
                <Layers size={18} className="text-accent-light" />
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-white truncate">{model.name}</p>
                    <CategoryPill category={model.category} />
                </div>
                <div className="flex items-center gap-3 mt-0.5">
                    {params && (
                        <span className="text-xs text-txt-muted">{params}</span>
                    )}
                    {family && (
                        <span className="text-xs text-txt-muted capitalize">{family}</span>
                    )}
                    <span className="text-xs text-txt-muted flex items-center gap-1">
                        <HardDrive size={10} />
                        {formatBytes(model.size)}
                    </span>
                </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-1 shrink-0">
                <button
                    onClick={() => onUpdate(model.name)}
                    disabled={isUpdating}
                    title="Update model"
                    className="btn-ghost text-xs py-1"
                >
                    <RefreshCw size={13} className={isUpdating ? 'animate-spin' : ''} />
                    {isUpdating ? 'Updating…' : 'Update'}
                </button>
                <button
                    onClick={() => onDelete(model.name)}
                    disabled={isUpdating}
                    title="Delete model"
                    className="btn-danger text-xs py-1"
                >
                    <Trash2 size={13} />
                    Delete
                </button>
            </div>
        </div>
    );
}
