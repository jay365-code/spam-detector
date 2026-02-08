import React from 'react';
import { Loader2, CheckCircle, Download } from 'lucide-react';

interface StatusPanelProps {
    current: number;
    total: number;
    isProcessing: boolean;
    startTime?: number | null; // Start Time
    endTime?: number | null;   // [New] End Time
    downloadUrl: string | null;
    onDownload?: () => void;
    isCancelling?: boolean;
    cancellationMessage?: string;
    onCancel?: () => void;
}

export const StatusPanel: React.FC<StatusPanelProps> = ({
    current,
    total,
    isProcessing,
    startTime,
    endTime,
    downloadUrl,
    onDownload,
    isCancelling = false,
    cancellationMessage = '',
    onCancel
}) => {
    // 처리 중이거나 다운로드 URL이 있으면 표시 (total이 0이어도 처리 중이면 표시)
    if (!isProcessing && !downloadUrl) return null;

    const percentage = total > 0 ? Math.round((current / total) * 100) : 0;

    // Timer Logic
    const [elapsed, setElapsed] = React.useState(0);

    React.useEffect(() => {
        let interval: ReturnType<typeof setInterval>;
        if (isProcessing && startTime) {
            setElapsed(Math.floor((Date.now() - startTime) / 1000)); // Reset initially
            interval = setInterval(() => {
                setElapsed(Math.floor((Date.now() - startTime) / 1000));
            }, 1000);
        } else if (!isProcessing && startTime && endTime) {
            // Fix invalid final time by using stored endTime
            setElapsed(Math.floor((endTime - startTime) / 1000));
        }
        return () => clearInterval(interval);
    }, [isProcessing, startTime, endTime]);

    // Format Seconds to HH:MM:SS
    const formatTime = (seconds: number) => {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    };

    return (
        <div className="relative w-full h-[78px] bg-slate-800 border border-slate-700 rounded-xl shadow-xl px-4 flex items-center animate-fade-in">
            <div className="flex-1 mr-4">
                <div className="flex justify-between items-center text-xs text-slate-400 mb-1.5">
                    <span className="flex items-center gap-2 font-medium text-slate-300">
                        {isProcessing ? (
                            <>
                                <Loader2 className="w-3 h-3 animate-spin text-blue-400" />
                                Processing...
                                {/* Timer Display */}
                                {startTime && (
                                    <span className="text-blue-300 font-mono bg-blue-500/10 px-1.5 rounded ml-1">
                                        {formatTime(elapsed)}
                                    </span>
                                )}
                            </>
                        ) : (
                            <>
                                <CheckCircle className="w-3 h-3 text-green-400" />
                                Completed
                                {/* Final Time Display */}
                                {startTime && (
                                    <span className="text-slate-400 font-mono ml-2 border-l border-slate-600 pl-2">
                                        Total: {formatTime(Math.floor(((endTime || Date.now()) - startTime) / 1000))}
                                    </span>
                                )}
                            </>
                        )}
                    </span>
                    <span className="font-mono">{current} / {total} ({percentage}%)</span>
                </div>

                <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                    <div
                        className={`h-2 rounded-full transition-all duration-300 ease-out ${isCancelling
                            ? 'bg-gradient-to-r from-red-500 to-orange-500'
                            : 'bg-gradient-to-r from-blue-500 to-purple-500'
                            }`}
                        style={{ width: `${percentage}%` }}
                    ></div>
                </div>

                {/* Cancellation Message */}
                {cancellationMessage && (
                    <div className="mt-2 text-xs text-yellow-400 flex items-center gap-1">
                        <span>⚠️</span>
                        <span>{cancellationMessage}</span>
                    </div>
                )}
            </div>

            {/* Cancel Button */}
            {isProcessing && onCancel && (
                <button
                    onClick={onCancel}
                    disabled={isCancelling}
                    className={`flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors shadow-lg whitespace-nowrap mr-2 ${isCancelling
                        ? 'bg-gray-500 cursor-not-allowed text-gray-300'
                        : 'bg-red-500 hover:bg-red-600 text-white shadow-red-500/20'
                        }`}
                >
                    {isCancelling ? '중지 요청됨' : '중지'}
                </button>
            )}

            {/* Download Button (Inline) - Using custom handler for Save As */}
            {downloadUrl && (
                <button
                    onClick={() => onDownload ? onDownload() : window.open(downloadUrl, '_blank')}
                    className="flex items-center justify-center gap-2 px-4 py-2 bg-green-500 hover:bg-green-600 text-white rounded-lg text-sm font-medium transition-colors shadow-lg shadow-green-500/20 whitespace-nowrap"
                >
                    <Download className="w-4 h-4" />
                    Download
                </button>
            )}
        </div>
    );
};

