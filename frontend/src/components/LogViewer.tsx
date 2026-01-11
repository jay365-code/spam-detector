import React, { useEffect, useRef } from 'react';
import { Terminal, XCircle, CheckCircle, AlertCircle } from 'lucide-react';

interface LogEntry {
    current: number;
    total: number;
    message: string;
    result?: {
        is_spam: boolean;
        spam_probability: number;
        reason: string;
        classification_code: string;
    }
}

interface LogViewerProps {
    logs: LogEntry[];
    isOpen: boolean;
    onToggle: () => void;
}

const CODE_MAP: Record<string, string> = {
    "1": "도박, 게임",
    "2": "성인 (유흥, 만남, 출장)",
    "3": "통신, 휴대폰",
    "4": "대리운전",
    "5": "불법 의약품",
    "6": "금융, 대출",
    "7": "구인/구직/부업",
    "8": "나이트클럽",
    "9": "주식 관련",
    "10": "로또",
    "30": "판단 보류 (HITL)",
    "HAM-1": "응답/알림/명세서",
    "HAM-2": "명확한 사업자 광고",
    "HAM-3": "생활 밀착형 정보/기타",
    "HAM-4": "간단 알림"
};

export const LogViewer: React.FC<LogViewerProps> = ({ logs, isOpen, onToggle }) => {
    const bottomRef = useRef<HTMLDivElement>(null);

    // Auto-scroll to bottom
    useEffect(() => {
        if (bottomRef.current) {
            bottomRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [logs]);

    const getCodeDescription = (rawCode?: string) => {
        if (!rawCode) return "Unk";
        const match = rawCode.match(/\d+/);
        const codeNum = match ? match[0] : rawCode;
        if (CODE_MAP[codeNum]) {
            return `${codeNum}. ${CODE_MAP[codeNum]}`;
        }
        return `${rawCode}. 기타`;
    };

    if (!isOpen) {
        return (
            <button
                onClick={onToggle}
                className="fixed bottom-4 right-4 bg-slate-800 text-white p-3 rounded-full shadow-lg hover:bg-slate-700 transition-all border border-slate-600"
            >
                <Terminal className="w-6 h-6" />
            </button>
        );
    }

    return (
        <div className="fixed bottom-0 left-0 right-0 h-64 bg-slate-900 border-t border-slate-700 shadow-2xl flex flex-col font-mono text-sm transition-transform duration-300">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2 bg-slate-800 border-b border-slate-700">
                <div className="flex items-center gap-2 text-slate-300">
                    <Terminal className="w-4 h-4" />
                    <span className="font-semibold">Analysis Logs</span>
                    <span className="bg-slate-700 px-2 py-0.5 rounded text-xs">
                        {logs.length} events
                    </span>
                </div>
                <button onClick={onToggle} className="text-slate-400 hover:text-white">
                    <XCircle className="w-5 h-5" />
                </button>
            </div>

            {/* Log Body */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2 bg-black/50">
                {logs.length === 0 && (
                    <div className="text-slate-500 text-center mt-10">
                        Waiting for analysis stream...
                    </div>
                )}

                {logs.map((log, idx) => (
                    <div key={idx} className="flex gap-3 items-start animate-fade-in group hover:bg-white/5 p-1 rounded">
                        <span className="text-slate-500 min-w-[30px]">
                            {String(idx + 1).padStart(3, '0')}
                        </span>

                        <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                                {log.result ? (
                                    log.result.is_spam ? (
                                        <span className="text-red-400 flex items-center gap-1 bg-red-400/10 px-1.5 rounded">
                                            <AlertCircle className="w-3 h-3" /> SPAM ({Math.round(log.result.spam_probability * 100)}%) - {getCodeDescription(log.result.classification_code)}
                                        </span>
                                    ) : (
                                        <span className="text-green-400 flex items-center gap-1 bg-green-400/10 px-1.5 rounded">
                                            <CheckCircle className="w-3 h-3" /> HAM
                                        </span>
                                    )
                                ) : (
                                    <span className="text-blue-400">Processing...</span>
                                )}
                                <span className="text-slate-400 ml-auto text-xs">
                                    [{log.current}/{log.total}]
                                </span>
                            </div>

                            <div className="text-slate-300 break-all">
                                {log.message}
                            </div>

                            {log.result && (
                                <div className="text-xs text-slate-500 mt-1 pl-2 border-l-2 border-slate-700">
                                    Reason: {log.result.reason}
                                </div>
                            )}
                        </div>
                    </div>
                ))}
                <div ref={bottomRef} />
            </div>
        </div>
    );
};
