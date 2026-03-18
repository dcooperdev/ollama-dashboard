import { useState, useEffect } from 'react';
import { apiGet } from '../../api/client.js';
import InstalledList from './InstalledList.jsx';
import AvailableList from './AvailableList.jsx';
import DownloadProgress from './DownloadProgress.jsx';
import { streamPost } from '../../api/client.js';

/**
 * ModelHub — top-level coordinator for the model management view.
 *
 * Responsibilities:
 *  - Fetches the curated "available" model catalogue from the backend.
 *  - Owns the pull state (which model is downloading + its progress).
 *  - Passes install / delete / update callbacks to child components.
 *
 * @param {{ installedModels: Array, onModelsChange: function }} props
 */
export default function ModelHub({ installedModels, onModelsChange }) {
    const [availableModels, setAvailableModels] = useState([]);
    const [pullState, setPullState] = useState(null); // null = idle

    // Fetch the static available-models catalogue once on mount.
    useEffect(() => {
        apiGet('/api/models/available')
            .then((d) => setAvailableModels(d.models ?? []))
            .catch(() => { }); // non-critical — the list is optional
    }, []);

    /** Installed model names for quick membership checks in AvailableList. */
    const installedNames = new Set(installedModels.map((m) => m.name));

    /**
     * Start an SSE pull stream for the given model name.
     * Progress is tracked in pullState; models list is refreshed on completion.
     *
     * @param {string} name - Ollama model tag, e.g. "llama3.2"
     */
    const handleInstall = async (name) => {
        setPullState({ name, status: 'Connecting…', progress: 0 });

        try {
            await streamPost('/api/models/pull', { name }, (event) => {
                if (event.error) {
                    setPullState((prev) => ({ ...prev, status: `Error: ${event.error}` }));
                    return;
                }

                const progress =
                    event.completed && event.total
                        ? Math.round((event.completed / event.total) * 100)
                        : null; // null = indeterminate (no byte counts yet)

                setPullState({
                    name,
                    status: event.status ?? 'Working…',
                    progress: progress ?? pullState?.progress ?? 0,
                });
            });
        } catch (err) {
            if (err.name !== 'AbortError') {
                setPullState((prev) => ({ ...prev, status: `Failed: ${err.message}` }));
                await new Promise((r) => setTimeout(r, 3000)); // let the user read the error
            }
        } finally {
            setPullState(null);
            onModelsChange(); // refresh the installed model list in App
        }
    };

    /**
     * Delete a model and refresh the installed list.
     * @param {string} name
     */
    const handleDelete = async (name) => {
        try {
            await fetch(`/api/models/${encodeURIComponent(name)}`, { method: 'DELETE' });
        } catch {
            // best-effort; the installed list will still refresh
        }
        onModelsChange();
    };

    /**
     * Update a model by re-pulling it (Ollama only downloads changed layers).
     * @param {string} name
     */
    const handleUpdate = (name) => handleInstall(name);

    return (
        <div className="h-full flex flex-col p-6 gap-6 overflow-y-auto animate-fade-in">
            {/* Download progress banner — shown while pulling */}
            {pullState && <DownloadProgress pullState={pullState} />}

            {/* Two-column layout: installed (wider) + available */}
            <div className="flex gap-6 flex-1 min-h-0">
                <InstalledList
                    models={installedModels}
                    pullingName={pullState?.name}
                    onDelete={handleDelete}
                    onUpdate={handleUpdate}
                />
                <AvailableList
                    models={availableModels}
                    installedNames={installedNames}
                    pullingName={pullState?.name}
                    onInstall={handleInstall}
                />
            </div>
        </div>
    );
}
