/**
 * CategoryPill — a compact, colored badge that communicates the capability
 * category of an Ollama model at a glance.
 *
 * Supported categories and their color schemes:
 *   - embedding  : amber  (warm warning — not for chat)
 *   - code       : cyan   (technical/dev feel)
 *   - vision     : purple (multimodal/creative)
 *   - reasoning  : orange (analytical/deep)
 *   - chat       : emerald (friendly/conversational)
 *
 * @param {{ category?: string, className?: string }} props
 */

// Color token map — one entry per supported category.
const PILL_STYLES = {
    embedding: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    code: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
    vision: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
    reasoning: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    chat: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
};

export default function CategoryPill({ category = 'chat', className = '' }) {
    const styles = PILL_STYLES[category] ?? PILL_STYLES.chat;

    return (
        <span
            className={[
                'inline-flex items-center text-[10px] font-semibold',
                'px-1.5 py-0.5 rounded-full border leading-none',
                'tracking-wide uppercase',
                styles,
                className,
            ].join(' ')}
        >
            {category}
        </span>
    );
}
