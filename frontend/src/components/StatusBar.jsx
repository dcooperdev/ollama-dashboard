import { useState, useEffect } from 'react';
import { Wifi, WifiOff, Cpu, CpuIcon } from 'lucide-react';
import { apiGet } from '../api/client.js';

// How often (ms) to re-poll the status endpoint.
const POLL_INTERVAL_MS = 10_000;

/**
 * StatusBar — compact connectivity indicators shown in the top header.
 *
 * Polls GET /api/status every POLL_INTERVAL_MS milliseconds and renders
 * animated coloured pills for internet and Ollama service health.
 */
export default function StatusBar() {
    const [status, setStatus] = useState({ internet: null, ollama: null });

    const fetchStatus = async () => {
        try {
            const data = await apiGet('/api/status');
            setStatus(data);
        } catch {
            // If the API itself is unreachable, mark everything as offline.
            setStatus({ internet: false, ollama: false });
        }
    };

    useEffect(() => {
        fetchStatus(); // initial probe on mount

        const id = setInterval(fetchStatus, POLL_INTERVAL_MS);
        return () => clearInterval(id); // clean up on unmount
    }, []);

    return (
        <div className="flex items-center gap-2">
            <StatusPill
                online={status.internet}
                label="Internet"
                OnIcon={Wifi}
                OffIcon={WifiOff}
            />
            <StatusPill
                online={status.ollama}
                label="Ollama"
                OnIcon={Cpu}
                OffIcon={CpuIcon}
            />
        </div>
    );
}

/**
 * A single coloured pill with an animated LED dot.
 *
 * @param {{ online: boolean|null, label: string, OnIcon: Component, OffIcon: Component }} props
 */
function StatusPill({ online, label, OnIcon, OffIcon }) {
    // null = initial loading state (show as neutral)
    const isLoading = online === null;
    const isOnline = !!online;

    const Icon = isOnline || isLoading ? OnIcon : OffIcon;

    if (isLoading) {
        return (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full
                      bg-white/5 border border-white/10 text-txt-muted text-xs font-medium">
                <div className="w-1.5 h-1.5 rounded-full bg-txt-muted animate-pulse-dot" />
                <Icon size={12} />
                <span>{label}</span>
            </div>
        );
    }

    return (
        <div className={isOnline ? 'pill-online' : 'pill-offline'}>
            {/* The LED dot animates when online to draw attention */}
            <div
                className={[
                    'w-1.5 h-1.5 rounded-full',
                    isOnline
                        ? 'bg-status-online animate-pulse-dot'
                        : 'bg-status-offline',
                ].join(' ')}
            />
            <Icon size={12} />
            <span>{label}</span>
        </div>
    );
}
