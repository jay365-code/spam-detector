import React from 'react';
import { Loader2, CheckCircle, Download } from 'lucide-react';

interface StatusPanelProps {
    current: number;
    total: number;
    isProcessing: boolean;
    startTime?: number | null; // Start Time
    endTime?: number | null;   // [New] End Time
    tokenUsage?: any;          // [New] Token Usage Data
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
    tokenUsage,
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
        <div className="flex items-center gap-3 w-full">
            <div className="relative flex-1 min-h-[78px] py-3 bg-slate-800 border border-slate-700 rounded-xl shadow-xl px-4 flex items-center animate-fade-in">
                <div className="flex-1 mr-4 flex flex-col justify-center">
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

                <div className="w-full justify-between items-center bg-slate-700 rounded-full h-2 overflow-hidden mb-1">
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
            
            {/* Token Usage UI (Completely Outside Main Box) */}
            {tokenUsage && Object.keys(tokenUsage).length > 0 && (
                <div className="flex items-center flex-col gap-1 min-w-[140px] max-h-[78px] overflow-y-auto custom-scrollbar bg-slate-800/60 border border-slate-700/60 p-2 rounded-xl shadow-md">
                    {Object.entries(tokenUsage).map(([model, usage]: [string, any]) => {
                        if (!usage.in && !usage.out) return null;
                        const tIn = (usage.in / 1000).toFixed(1) + 'k';
                        const tOut = (usage.out / 1000).toFixed(1) + 'k';
                        
                        let colorClass = 'text-slate-300';
                        const modelLower = model.toLowerCase();
                        if (modelLower.includes('gemini')) colorClass = 'text-blue-400';
                        else if (modelLower.includes('gpt')) colorClass = 'text-green-400';
                        else if (modelLower.includes('claude')) colorClass = 'text-purple-400';

                        return (
                            <div key={model} className="flex flex-col w-full bg-slate-900/80 border border-slate-700/80 px-2 py-1 rounded">
                                <span className={`font-bold ${colorClass} text-[10px] truncate max-w-[120px]`} title={model}>{model}</span>
                                <div className="flex gap-1 text-[9px] text-slate-400 font-mono tracking-tighter">
                                    <span>I:{tIn}</span>
                                    <span className="text-slate-600">|</span>
                                    <span>O:{tOut}</span>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

