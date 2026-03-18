import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import DownloadProgress from './DownloadProgress';

describe('DownloadProgress', () => {
    it('returns null if no state', () => {
        const { container } = render(<DownloadProgress pullState={null} />);
        expect(container).toBeEmptyDOMElement();
    });

    it('renders indeterminate state correctly', () => {
        render(<DownloadProgress pullState={{ name: 'llama3', status: 'pulling manifest', progress: 0 }} />);
        expect(screen.getByText('llama3')).toBeInTheDocument();
        expect(screen.getByText('pulling manifest')).toBeInTheDocument();
        expect(screen.queryByText('%')).not.toBeInTheDocument();
    });

    it('renders determinate progress', () => {
        render(<DownloadProgress pullState={{ name: 'llama3', status: 'downloading...', progress: 45 }} />);
        expect(screen.getByText('45%')).toBeInTheDocument();
        expect(screen.getByText('downloading...')).toBeInTheDocument();
    });
});
