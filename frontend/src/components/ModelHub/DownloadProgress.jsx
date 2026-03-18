import { ArrowDownToLine } from 'lucide-react';

/**
 * DownloadProgress — sticky banner displayed while a model pull is in progress.
 *
 * Renders the model name, a human-readable status text, and a progress bar.
 * The bar switches between a determinate fill (when byte counts are available)
 * and an indeterminate shimmer (during manifest pull / digest verification).
 *
 * @param {{
 *   pullState: { name: string, status: string, progress: number } | null
 * }} props
 */
export default function DownloadProgress({ pullState }) {
    if (!pullState) return null;

    const { name, status, progress } = pullState;

    // progress === 0 with no data yet → show indeterminate shimmer
    const isIndeterminate = progress === 0 && !status.includes('%');

    return (
        <div
            className="card border-accent/20 bg-accent/5 p-4
                 flex items-center gap-4 animate-slide-up"
        >
            {/* Icon */}
            <div
                className="flex items-center justify-center w-9 h-9 rounded-lg
                      bg-accent/15 border border-accent/25 shrink-0"
            >
                <ArrowDownToLine size={16} className="text-accent-light" />
            </div>

            {/* Text + bar */}
            <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1.5">
                    <p className="text-sm font-semibold text-white truncate">{name}</p>
                    {!isIndeterminate && (
                        <span className="text-xs font-mono text-accent-light ml-3 shrink-0">
                            {progress}%
                        </span>
                    )}
                </div>

                {/* Progress track */}
                <div className="h-1.5 rounded-full bg-surface-raised overflow-hidden">
                    {isIndeterminate ? (
                        /* Indeterminate shimmer bar */
                        <div
                            className="h-full w-1/3 rounded-full
                            bg-gradient-to-r from-transparent via-accent to-transparent
                            animate-shimmer"
                            style={{ backgroundSize: '200% 100%' }}
                        />
                    ) : (
                        /* Determinate fill bar */
                        <div
                            className="h-full rounded-full
                            bg-gradient-to-r from-accent-dark to-accent
                            transition-all duration-300 ease-out"
                            style={{ width: `${progress}%` }}
                        />
                    )}
                </div>

                {/* Status text */}
                <p className="text-[11px] text-txt-secondary mt-1 truncate capitalize">
                    {status}
                </p>
            </div>
        </div>
    );
}
