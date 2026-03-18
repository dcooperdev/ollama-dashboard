import { useState, useMemo } from 'react';
import { Download, CheckCircle2, Loader2, Search, ArrowUpDown } from 'lucide-react';
import CategoryPill from '../CategoryPill.jsx';

/**
 * Parse a human-readable size string into a numeric value in GB for sorting.
 * Examples: "2.0 GB" → 2.0  |  "670 MB" → 0.67  |  "40 GB" → 40
 *
 * @param {string} sizeStr - Size string from the model catalogue
 * @returns {number}
 */
function parseSizeGB(sizeStr = '') {
    const match = sizeStr.match(/([\d.]+)\s*(GB|MB|KB)/i);
    if (!match) return 0;
    const value = parseFloat(match[1]);
    const unit = match[2].toUpperCase();
    if (unit === 'GB') return value;
    if (unit === 'MB') return value / 1024;
    if (unit === 'KB') return value / (1024 * 1024);
    return 0;
}

// Sort options shown in the dropdown
const SORT_OPTIONS = [
    { value: 'default', label: 'Default order' },
    { value: 'size-asc', label: 'Size: smallest first' },
    { value: 'size-desc', label: 'Size: largest first' },
];

/**
 * AvailableList — renders the curated catalogue of downloadable models.
 *
 * Includes a filter bar with:
 *  - Text search: filters by model name, display name, or description.
 *  - Sort control: orders by catalogue position, size ascending, or size descending.
 *
 * All filtering and sorting are pure computed values (useMemo) — no server
 * calls or additional dependencies required.
 *
 * @param {{
 *   models: Array,
 *   installedNames: Set<string>,
 *   pullingName: string|null,
 *   onInstall: function,
 * }} props
 */
export default function AvailableList({ models, installedNames, pullingName, onInstall }) {
    // !!pullingName is falsy for both null and undefined — the prop arrives as
    // undefined (not null) when pullState is null, so strict !== null was always true.
    const isBusy = !!pullingName; // true only when an actual model name string is present


    // ---- Filter & sort state ------------------------------------------------
    const [search, setSearch] = useState('');
    const [sortBy, setSortBy] = useState('default');

    /** Derived list: filtered by search query, then sorted by the chosen criterion. */
    const visibleModels = useMemo(() => {
        const q = search.trim().toLowerCase();

        // Step 1 — filter: match against name, display label, and description
        const filtered = q
            ? models.filter(
                (m) =>
                    (m.name ?? '').toLowerCase().includes(q) ||
                    (m.display ?? '').toLowerCase().includes(q) ||
                    (m.description ?? '').toLowerCase().includes(q),
            )
            : models;

        // Step 2 — sort: default keeps the original catalogue order
        if (sortBy === 'default') return filtered;

        return [...filtered].sort((a, b) => {
            const diff = parseSizeGB(a.size) - parseSizeGB(b.size);
            return sortBy === 'size-asc' ? diff : -diff;
        });
    }, [models, search, sortBy]);

    return (
        <section className="flex flex-col flex-[2] min-w-0">
            {/* Section header */}
            <div className="mb-3">
                <h2 className="text-base font-semibold text-white">Available Models</h2>
                <p className="text-xs text-txt-secondary mt-0.5">
                    {visibleModels.length} of {models.length} models
                </p>
            </div>

            {/* ---- Filter bar ---- */}
            <div className="flex gap-2 mb-3">
                {/* Search input */}
                <div className="relative flex-1">
                    <Search
                        size={13}
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-txt-muted pointer-events-none"
                    />
                    <input
                        type="text"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Filter by name…"
                        className="input pl-8 py-2 text-xs"
                    />
                </div>

                {/* Sort dropdown */}
                <div className="relative shrink-0">
                    <ArrowUpDown
                        size={12}
                        className="absolute left-2.5 top-1/2 -translate-y-1/2 text-txt-muted pointer-events-none"
                    />
                    <select
                        value={sortBy}
                        onChange={(e) => setSortBy(e.target.value)}
                        className="input pl-7 pr-3 py-2 text-xs appearance-none cursor-pointer
                       bg-surface-raised min-w-[160px]"
                    >
                        {SORT_OPTIONS.map(({ value, label }) => (
                            <option key={value} value={value}>
                                {label}
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            {/* ---- Empty search result ---- */}
            {visibleModels.length === 0 && (
                <div className="card flex flex-col items-center justify-center py-10 text-center">
                    <Search size={24} className="text-txt-muted mb-2 opacity-40" />
                    <p className="text-sm text-txt-secondary">No models match "{search}"</p>
                    <button
                        onClick={() => setSearch('')}
                        className="btn-ghost text-xs mt-2"
                    >
                        Clear filter
                    </button>
                </div>
            )}

            {/* ---- Model cards ---- */}
            <div className="flex flex-col gap-3 overflow-y-auto pr-1">
                {visibleModels.map((model) => {
                    const installed = installedNames.has(model.name);
                    const isThisOne = pullingName === model.name;

                    return (
                        <div
                            key={model.name}
                            className="card p-4 flex flex-col gap-2
                         transition-all duration-200 hover:border-white/10
                         animate-slide-up"
                        >
                            {/* Header row */}
                            <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                    <div className="flex items-center gap-2">
                                        <p className="text-sm font-semibold text-white truncate">
                                            {model.display ?? model.name}
                                        </p>
                                        {model.category && <CategoryPill category={model.category} />}
                                    </div>
                                    <p className="text-[11px] text-txt-muted font-mono">{model.name}</p>
                                </div>

                                {/* Install / installed badge */}
                                {installed ? (
                                    <span
                                        className="flex items-center gap-1 text-xs text-status-online
                               px-2 py-1 rounded-full bg-status-online/10
                               border border-status-online/20 shrink-0"
                                    >
                                        <CheckCircle2 size={11} />
                                        Installed
                                    </span>
                                ) : (
                                    <button
                                        onClick={() => onInstall(model.name)}
                                        disabled={isBusy}
                                        className="btn-primary text-xs py-1.5 px-3 shrink-0"
                                    >
                                        {isThisOne ? (
                                            <>
                                                <Loader2 size={12} className="animate-spin" />
                                                Pulling…
                                            </>
                                        ) : (
                                            <>
                                                <Download size={12} />
                                                Install
                                            </>
                                        )}
                                    </button>
                                )}
                            </div>

                            {/* Description */}
                            <p className="text-xs text-txt-secondary leading-relaxed">
                                {model.description}
                            </p>

                            {/* Meta: parameters + size + tags */}
                            <div className="flex items-center gap-2 flex-wrap mt-0.5">
                                {model.parameters && (
                                    <span className="text-[10px] font-mono text-txt-muted
                                   bg-surface-raised px-1.5 py-0.5 rounded">
                                        {model.parameters}
                                    </span>
                                )}
                                <span className="text-[10px] font-mono text-txt-muted
                                 bg-surface-raised px-1.5 py-0.5 rounded">
                                    {model.size}
                                </span>
                                {(model.tags ?? []).map((tag) => (
                                    <span
                                        key={tag}
                                        className="text-[10px] text-accent/70
                               bg-accent/8 border border-accent/15
                               px-1.5 py-0.5 rounded"
                                    >
                                        {tag}
                                    </span>
                                ))}
                            </div>
                        </div>
                    );
                })}
            </div>
        </section>
    );
}
