/** @type {import('tailwindcss').Config} */
export default {
    content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
    theme: {
        extend: {
            // --------------- Colour palette ---------------
            colors: {
                // Dark background layers — deepest to most elevated
                surface: {
                    deep: '#080810',
                    base: '#0f0f1e',
                    card: '#161628',
                    raised: '#1e1e38',
                },
                // Purple accent hierarchy
                accent: {
                    DEFAULT: '#8b5cf6',
                    light: '#a78bfa',
                    dark: '#6d28d9',
                    dim: 'rgba(139,92,246,0.15)',
                    glow: 'rgba(139,92,246,0.30)',
                },
                // Semantic text colours
                txt: {
                    primary: '#e8e8ff',
                    secondary: '#7070a8',
                    muted: '#4a4a68',
                },
                // Status indicators
                status: {
                    online: '#10b981',
                    offline: '#ef4444',
                    warning: '#f59e0b',
                },
            },

            // --------------- Typography ---------------
            fontFamily: {
                sans: ['Inter', 'system-ui', 'sans-serif'],
                mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
            },

            // --------------- Shadows ---------------
            boxShadow: {
                accent: '0 0 24px rgba(139,92,246,0.25)',
                card: '0 4px 24px rgba(0,0,0,0.45)',
                'inner-subtle': 'inset 0 1px 0 rgba(255,255,255,0.04)',
                glow: '0 0 40px rgba(139,92,246,0.2)',
            },

            // --------------- Animations ---------------
            animation: {
                'pulse-dot': 'pulseDot 2.4s ease-in-out infinite',
                'slide-up': 'slideUp 0.28s cubic-bezier(0.16,1,0.3,1)',
                'fade-in': 'fadeIn 0.2s ease-out',
                shimmer: 'shimmer 2s linear infinite',
                blink: 'blink 1.1s step-end infinite',
            },
            keyframes: {
                pulseDot: {
                    '0%,100%': { opacity: '1', transform: 'scale(1)' },
                    '50%': { opacity: '0.35', transform: 'scale(0.8)' },
                },
                slideUp: {
                    from: { opacity: '0', transform: 'translateY(12px)' },
                    to: { opacity: '1', transform: 'translateY(0)' },
                },
                fadeIn: {
                    from: { opacity: '0' },
                    to: { opacity: '1' },
                },
                shimmer: {
                    '0%': { backgroundPosition: '-200% 0' },
                    '100%': { backgroundPosition: '200% 0' },
                },
                blink: {
                    '0%,100%': { opacity: '1' },
                    '50%': { opacity: '0' },
                },
            },
        },
    },
    plugins: [],
};
