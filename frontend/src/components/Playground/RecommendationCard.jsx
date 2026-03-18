import { useState } from 'react';
import { DownloadCloud, Play, AlertCircle, Loader2, CheckCircle2 } from 'lucide-react';

/**
 * An interactive card that appears when the orchestrator recommends
 * installing an ideal expert model for the user's task.
 * 
 * @param {{
 *   target: string,
 *   reason: string,
 *   onInstallSuccess: (modelName: string) => void,
 *   onSkip: () => void
 * }} props 
 */
export default function RecommendationCard({ target, reason, onInstallSuccess, onSkip }) {
    const [installing, setInstalling] = useState(false);
    const [progress, setProgress] = useState(0);
    const [statusText, setStatusText] = useState('');
    const [error, setError] = useState(null);

    const handleInstall = async () => {
        setInstalling(true);
        setError(null);
        setProgress(0);
        setStatusText(`Pulling ${target}...`);

        try {
            // Using the native fetch to stream the pull response
            const res = await fetch('http://localhost:8000/api/models/pull', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: target })
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || `HTTP error ${res.status}`);
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n').filter(Boolean);

                for (const line of lines) {
                    if (line.trim() === 'data: [DONE]') continue;

                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.status) setStatusText(data.status);
                            if (data.completed && data.total) {
                                setProgress((data.completed / data.total) * 100);
                            }
                            if (data.error) throw new Error(data.error);
                        } catch (e) {
                            // ignore parse errors for partial chunks
                        }
                    }
                }
            }

            // Successfully pulled
            setStatusText('Complete!');
            setProgress(100);

            // Give the UI a brief moment to show 100%
            setTimeout(() => {
                onInstallSuccess(target);
            }, 800);

        } catch (err) {
            setError(err.message);
            setInstalling(false);
        }
    };

    return (
        <div className="w-full max-w-2xl mx-auto my-4 overflow-hidden rounded-2xl border border-accent/20 bg-surface-base/60 backdrop-blur-md shadow-lg flex flex-col animate-fade-in-up origin-bottom">
            <div className="px-5 py-4 flex items-start gap-4 border-b border-white/[0.05]">
                <div className="mt-1 flex-shrink-0 w-10 h-10 rounded-full bg-accent/20 flex items-center justify-center border border-accent/30 text-accent-light">
                    <AlertCircle size={20} />
                </div>
                <div className="flex-1">
                    <h3 className="text-lg font-semibold text-white tracking-tight">
                        Missing ideal specialist
                    </h3>
                    <p className="text-sm text-txt-secondary mt-1 max-w-[90%] leading-relaxed">
                        {reason}
                    </p>
                    <div className="mt-2 inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-black/40 border border-white/5">
                        <span className="text-xs font-medium text-txt-muted uppercase tracking-wider">Recommended Model</span>
                        <code className="text-xs font-mono text-accent-light bg-accent/10 px-1.5 py-0.5 rounded">{target}</code>
                    </div>
                </div>
            </div>

            <div className="px-5 py-3.5 bg-black/20 flex items-center justify-end gap-3">
                {error && (
                    <span className="text-xs text-red-400 font-medium mr-auto truncate max-w-[200px]" title={error}>
                        {error}
                    </span>
                )}

                {installing ? (
                    <div className="flex-1 flex items-center gap-4 mr-2">
                        <div className="flex-1 bg-surface-elevated h-2.5 rounded-full overflow-hidden border border-white/5">
                            <div
                                className="h-full bg-accent transition-all duration-300 ease-out"
                                style={{ width: `${Math.max(5, progress)}%` }}
                            />
                        </div>
                        <span className="text-xs font-medium text-txt-secondary whitespace-nowrap min-w-[120px]">
                            {statusText}
                        </span>
                    </div>
                ) : (
                    <>
                        <button
                            onClick={onSkip}
                            className="btn-ghost text-sm px-4 py-1.5 flex items-center gap-2"
                        >
                            <Play size={16} className="text-txt-muted" />
                            <span>Continue without it</span>
                        </button>

                        <button
                            onClick={handleInstall}
                            className="btn-primary text-sm px-5 py-1.5 flex items-center gap-2 shadow-accent/20"
                        >
                            <DownloadCloud size={16} className="opacity-90" />
                            <span>Install now</span>
                        </button>
                    </>
                )}
            </div>
        </div>
    );
}
