import { useState, useEffect, useCallback } from 'react';
import { Bot, LayoutGrid, FlaskConical, ChevronRight } from 'lucide-react';
import { apiGet } from './api/client.js';
import StatusBar from './components/StatusBar.jsx';
import ModelHub from './components/ModelHub/ModelHub.jsx';
import Playground from './components/Playground/Playground.jsx';

/**
 * Root application component.
 *
 * Manages two pieces of state that multiple child components share:
 *  - installedModels : list returned by GET /api/models (refreshed after install/delete)
 *  - selectedModel   : the model tag currently chosen in the Playground
 *
 * View routing between "hub" and "playground" is handled here with a simple
 * string-state flag — no router library is needed for two views.
 */
export default function App() {
    const [view, setView] = useState('hub'); // 'hub' | 'playground'
    const [installedModels, setInstalledModels] = useState([]);
    const [selectedModel, setSelectedModel] = useState('');
    const [loadingModels, setLoadingModels] = useState(true);

    // Fetch the installed model list; called on mount and after any install/delete.
    const refreshModels = useCallback(async () => {
        try {
            const data = await apiGet('/api/models');
            const models = data.models ?? [];
            setInstalledModels(models);

            // Auto-select the first model if nothing is selected yet.
            setSelectedModel((prev) =>
                prev && models.some((m) => m.name === prev) ? prev : models[0]?.name ?? '',
            );
        } catch {
            // Ollama may be offline; keep whatever we had before.
        } finally {
            setLoadingModels(false);
        }
    }, []);

    useEffect(() => {
        refreshModels();
    }, [refreshModels]);

    // ---- Sidebar navigation items ----
    const navItems = [
        { id: 'hub', label: 'Model Hub', icon: LayoutGrid },
        { id: 'playground', label: 'Playground', icon: FlaskConical },
    ];

    return (
        <div className="flex h-full bg-surface-deep overflow-hidden">
            {/* ================================================================ */}
            {/* Sidebar                                                           */}
            {/* ================================================================ */}
            <aside className="flex flex-col w-60 shrink-0 bg-surface-base border-r border-white/[0.05] py-5 px-3">
                {/* Logo */}
                <div className="flex items-center gap-2.5 px-3 mb-8">
                    <div
                        className="flex items-center justify-center w-8 h-8 rounded-lg
                          bg-gradient-to-br from-accent to-accent-dark shadow-accent"
                    >
                        <Bot size={17} className="text-white" />
                    </div>
                    <div>
                        <p className="text-sm font-bold text-white leading-none">Ollama</p>
                        <p className="text-[10px] text-txt-muted leading-none mt-0.5 font-mono">
                            Dashboard
                        </p>
                    </div>
                </div>

                {/* Nav */}
                <nav className="flex flex-col gap-1 flex-1">
                    <p className="section-header px-3">Navigation</p>
                    {navItems.map(({ id, label, icon: Icon }) => (
                        <button
                            key={id}
                            onClick={() => setView(id)}
                            className={view === id ? 'nav-item-active' : 'nav-item'}
                        >
                            <Icon size={16} />
                            <span className="flex-1 text-left">{label}</span>
                            {view === id && (
                                <ChevronRight size={14} className="text-accent opacity-60" />
                            )}
                        </button>
                    ))}
                </nav>

                {/* Footer: model count badge */}
                <div className="px-3 pt-4 border-t border-white/[0.05]">
                    <div className="flex items-center justify-between">
                        <span className="text-xs text-txt-muted">Installed models</span>
                        <span
                            className="text-xs font-semibold bg-accent/15 text-accent-light
                            px-2 py-0.5 rounded-full"
                        >
                            {loadingModels ? '…' : installedModels.length}
                        </span>
                    </div>
                    <p className="text-[10px] text-txt-muted mt-2 font-mono">v1.0.0</p>
                </div>
            </aside>

            {/* ================================================================ */}
            {/* Main content                                                       */}
            {/* ================================================================ */}
            <div className="flex flex-col flex-1 min-w-0">
                {/* Top bar */}
                <header
                    className="flex items-center justify-between shrink-0
                        px-6 h-14 border-b border-white/[0.05] bg-surface-base/50
                        backdrop-blur-sm"
                >
                    <h1 className="text-sm font-semibold text-white">
                        {view === 'hub' ? 'Model Hub' : 'Playground'}
                    </h1>
                    <StatusBar />
                </header>

                {/* Page content — scrolls independently */}
                <main className="flex-1 overflow-hidden">
                    {view === 'hub' ? (
                        <ModelHub
                            installedModels={installedModels}
                            onModelsChange={refreshModels}
                        />
                    ) : (
                        <Playground
                            installedModels={installedModels}
                            selectedModel={selectedModel}
                            onModelSelect={setSelectedModel}
                        />
                    )}
                </main>
            </div>
        </div>
    );
}
