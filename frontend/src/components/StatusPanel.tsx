import React from 'react';
import { Loader2, CheckCircle, Download } from 'lucide-react';

interface StatusPanelProps {
    current: number;
    total: number;
    isProcessing: boolean;
    downloadUrl: string | null;
    filename: string | null;
}

export const StatusPanel: React.FC<StatusPanelProps> = ({ current, total, isProcessing, downloadUrl, filename }) => {
    if ((!isProcessing && !downloadUrl) || total === 0) return null;

    const percentage = total > 0 ? Math.round((current / total) * 100) : 0;

    return (
        <div className="relative w-full h-[78px] bg-slate-800 border border-slate-700 rounded-xl shadow-xl px-4 flex items-center animate-fade-in">
            <div className="flex-1 mr-4">
                <div className="flex justify-between items-center text-xs text-slate-400 mb-1.5">
                    <span className="flex items-center gap-2 font-medium text-slate-300">
                        {isProcessing ? (
                            <>
                                <Loader2 className="w-3 h-3 animate-spin text-blue-400" />
                                Processing...
                            </>
                        ) : (
                            <>
                                <CheckCircle className="w-3 h-3 text-green-400" />
                                Completed
                            </>
                        )}
                    </span>
                    <span className="font-mono">{current} / {total} ({percentage}%)</span>
                </div>

                <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                    <div
                        className="bg-gradient-to-r from-blue-500 to-purple-500 h-2 rounded-full transition-all duration-300 ease-out"
                        style={{ width: `${percentage}%` }}
                    ></div>
                </div>
            </div>

            {/* Download Button (Inline) */}
            {downloadUrl && (
                <a
                    href={downloadUrl}
                    download={filename || "result.xlsx"}
                    className="flex items-center justify-center gap-2 px-4 py-2 bg-green-500 hover:bg-green-600 text-white rounded-lg text-sm font-medium transition-colors shadow-lg shadow-green-500/20 whitespace-nowrap"
                >
                    <Download className="w-4 h-4" />
                    Download
                </a>
            )}
        </div>
    );
};
