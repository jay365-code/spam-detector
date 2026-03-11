import React, { useState } from 'react';
import axios from 'axios';
import { Upload, FileSpreadsheet, RefreshCw, AlertCircle, ChevronRight, BarChart3, Search, Download, Check, Database, Copy, GitCompare, X } from 'lucide-react';
import { RagRegistrationModal } from '../RagRegistrationModal';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// --- Utility ---
function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

// --- Types ---
interface SummaryMetrics {
    sheet_used: string;
    total_human: number;
    total_llm: number;
    human_spam_count: number;
    llm_spam_count: number;
    human_spam_rate: number;
    llm_spam_rate: number;
    matched: number;
    match_rate: number;
    agreement_rate: number;
    tp: number;
    fp: number;
    fn: number;
    tn: number;
    precision: number;
    recall: number;
    f1: number;
    // 주요 지표
    accuracy: number;
    kappa: number;
    kappa_status: string;
    mcc: number;
    disagreement_rate: number;
    // 주요 판정 (Accuracy + Kappa 기반)
    primary_status: string;
    primary_color: 'success' | 'warning' | 'danger';
    primary_description: string;
    // 보조 지표 (HEI)
    hei: number;
    hei_status: string;
    hei_color: 'success' | 'warning' | 'danger';
}

interface DiffItem {
    diff_id: string;
    diff_type: "FN" | "FP";
    message_preview: string;
    message_full: string;
    human_label_raw: string;
    llm_label_raw: string;
    human_code?: string;
    llm_code?: string;
    human_is_spam: boolean;
    llm_is_spam: boolean;
    human_reason?: string;
    llm_reason?: string;
    match_key: string;
    policy_interpretation?: string;
}

interface MissingRecord {
    index: number;
    message: string;
    label: string;
    code: string;
    reason: string;
}

interface CompareResponse {
    summary: SummaryMetrics;
    diffs: DiffItem[];
    missing_in_human: MissingRecord[];
    missing_in_llm: MissingRecord[];
    auto_summary: string;
}

// --- Components ---

const StatCard = ({ title, value, subValue, description, type = 'neutral' }: { title: string, value: string | number, subValue?: string, description?: string, type?: 'neutral' | 'success' | 'danger' | 'warning' | 'brand' }) => {
    const styles = {
        neutral: 'bg-white border-gray-200 text-gray-900',
        success: 'bg-emerald-50 border-emerald-200 text-emerald-800',
        danger: 'bg-rose-50 border-rose-200 text-rose-800',
        warning: 'bg-amber-50 border-amber-200 text-amber-800',
        brand: 'bg-indigo-600 border-indigo-500 text-white shadow-lg shadow-indigo-200 ring-1 ring-indigo-500',
    };

    return (
        <div className={cn("relative group p-5 rounded-2xl border shadow-sm transition-all hover:shadow-md cursor-help", styles[type])}>
            <p className={cn("text-xs font-bold uppercase tracking-wider mb-1 flex items-center gap-1", type === 'brand' ? 'opacity-90 text-indigo-100' : 'opacity-70')}>
                {title}
                {description && <AlertCircle size={10} className={cn("opacity-50", type === 'brand' ? "text-indigo-200" : "")} />}
            </p>
            <div className="flex items-baseline gap-2">
                <p className="text-3xl font-extrabold">{value}</p>
                {subValue && <span className={cn("text-xs font-medium", type === 'brand' ? "text-indigo-200 opacity-100" : "opacity-80")}>{subValue}</span>}
            </div>

            {/* Tooltip */}
            {description && (
                <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 w-52 p-3 bg-slate-900 text-white text-xs rounded-xl shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 pointer-events-none leading-relaxed border border-slate-700">
                    <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-slate-900 rotate-45 border-t border-l border-slate-700"></div>
                    {description}
                </div>
            )}
        </div>
    );
};

const FileInput = ({ label, onChange, file }: { label: string, onChange: (e: React.ChangeEvent<HTMLInputElement>) => void, file: File | null }) => (
    <div className="space-y-2">
        <label className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <FileSpreadsheet size={16} /> {label}
        </label>
        <div className={cn("relative group transition-all rounded-xl border-2 border-dashed p-4 hover:bg-gray-50 flex flex-col items-center justify-center text-center cursor-pointer", file ? "border-solid bg-gray-50 border-gray-300" : "border-gray-300")}>
            <input
                type="file"
                onChange={onChange}
                accept=".xlsx"
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
            />
            {file ? (
                <div className="text-sm text-gray-800 font-medium truncate w-full px-2">
                    {file.name}
                </div>
            ) : (
                <div className="text-gray-400 group-hover:text-gray-600 transition-colors">
                    <Upload className="mx-auto mb-2 opacity-50" size={24} />
                    <span className="text-xs">Click to upload .xlsx</span>
                </div>
            )}
        </div>
    </div>
);

export default function ValidatorPage() {
    const [humanFile, setHumanFile] = useState<File | null>(null);
    const [llmFile, setLlmFile] = useState<File | null>(null);
    const [sheetName, setSheetName] = useState("육안분석(시뮬결과35_150)");
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState<CompareResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isConfigOpen, setIsConfigOpen] = useState(true);

    // Auto Mode State
    const getTodayYYYYMMDD = () => {
        const d = new Date();
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}${month}${day}`;
    };

    const [isAutoMode, setIsAutoMode] = useState(true);
    const [autoDate, setAutoDate] = useState(getTodayYYYYMMDD());
    const [autoType, setAutoType] = useState("A");


    // Viewer State
    const [selectedDiff, setSelectedDiff] = useState<DiffItem | null>(null);
    const [filter, setFilter] = useState<'ALL' | 'FN' | 'FP'>('ALL');
    const [searchTerm, setSearchTerm] = useState('');
    const [copied, setCopied] = useState(false);
    const [isDiffModalOpen, setIsDiffModalOpen] = useState(false);

    // RAG Save State
    const [ragSaveStatus, setRagSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');
    const [ragSaveMessage, setRagSaveMessage] = useState('');
    const [isRagModalOpen, setIsRagModalOpen] = useState(false);
    const [ragModalData, setRagModalData] = useState<{
        message: string;
        label: string;
        code: string;
        diffType: 'FN' | 'FP';
        reason: string;
    } | null>(null);

    // RAG 등록 모달 열기
    const handleOpenRagModal = (diff: DiffItem) => {
        setRagModalData({
            message: diff.message_full,
            label: diff.human_is_spam ? 'SPAM' : 'HAM',
            code: diff.human_code || '',
            diffType: diff.diff_type,
            reason: diff.human_reason || ''
        });
        setIsRagModalOpen(true);
    };

    // RAG 최종 저장 함수 (모달에서 호출)
    const handleSaveToRag = async (payload: any) => {
        try {
            await axios.post('http://localhost:8000/api/spam-rag', payload);
            setRagSaveStatus('success');
            setRagSaveMessage('RAG에 저장되었습니다');
            setTimeout(() => setRagSaveStatus('idle'), 3000);
        } catch (err: any) {
            if (err.response && err.response.status === 409) {
                throw new Error('이미 등록된 메시지입니다.');
            } else {
                throw new Error('RAG 서버 저장 중 오류가 발생했습니다.');
            }
        }
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>, setter: (f: File | null) => void) => {
        if (e.target.files && e.target.files[0]) {
            setter(e.target.files[0]);
        }
    };

    const handleCompare = async () => {
        setLoading(true);
        setError(null);
        setData(null);
        setSelectedDiff(null);

        try {
            let res;
            if (isAutoMode) {
                if (!autoDate || !autoType) {
                    setError("Please enter both Date and Type.");
                    setLoading(false);
                    return;
                }
                const formData = new FormData();
                formData.append("date", autoDate);
                formData.append("file_type", autoType);
                formData.append("sheet_name", sheetName);

                res = await axios.post("http://localhost:8001/compare/auto", formData, {
                    headers: { "Content-Type": "multipart/form-data" },
                });
            } else {
                if (!humanFile || !llmFile) {
                    setError("Please select both files.");
                    setLoading(false);
                    return;
                }
                const formData = new FormData();
                formData.append("human_file", humanFile);
                formData.append("llm_file", llmFile);
                formData.append("sheet_name", sheetName);

                res = await axios.post("http://localhost:8001/compare", formData, {
                    headers: { "Content-Type": "multipart/form-data" },
                });
            }
            setData(res.data);
            setIsConfigOpen(false); // Auto close on success
        } catch (err: any) {
            console.error(err);
            setError(err.response?.data?.detail || "An error occurred during comparison.");
        } finally {
            setLoading(false);
        }
    };

    const filteredDiffs = data?.diffs.filter(d => {
        if (filter !== 'ALL' && d.diff_type !== filter) return false;
        if (searchTerm && !d.message_full.toLowerCase().includes(searchTerm.toLowerCase())) return false;
        return true;
    });

    // 탭별 개수 계산
    const diffCounts = {
        ALL: data?.diffs.length ?? 0,
        FN: data?.diffs.filter(d => d.diff_type === 'FN').length ?? 0,
        FP: data?.diffs.filter(d => d.diff_type === 'FP').length ?? 0,
    };

    // 텍스트 다운로드 함수 (메시지 원본만)
    const handleDownloadText = (targetFilter: 'ALL' | 'FN' | 'FP') => {
        if (!data?.diffs) return;

        const targetDiffs = data.diffs.filter(d => {
            if (targetFilter !== 'ALL' && d.diff_type !== targetFilter) return false;
            return true;
        });

        if (targetDiffs.length === 0) {
            alert(`${targetFilter} 항목이 없습니다.`);
            return;
        }

        // 메시지 원본만 추출 (한 줄에 하나씩)
        const textContent = targetDiffs.map(diff => diff.message_full).join('\n');

        const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `spam_validator_${targetFilter.toLowerCase()}_${new Date().toISOString().slice(0, 10)}.txt`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    // JSON 저장 함수
    const handleSaveJson = async () => {
        if (!data || !humanFile) return;

        // 파일명에서 날짜와 식별자 추출 (예: MMSC스팸추출_20260101_A.xlsx -> 20260101_A)
        const match = humanFile.name.match(/(\d{8})_([A-Z])/);
        let filename = 'comparison_result.json';

        if (match) {
            const [_, date, type] = match;
            filename = `일별비교_${date}_${type}.json`;
        }

        const jsonString = JSON.stringify(data, null, 2);

        try {
            // Modern browsers: Show "Save As" dialog
            // @ts-ignore: File System Access API might missing in types
            if (window.showSaveFilePicker) {
                // @ts-ignore
                const handle = await window.showSaveFilePicker({
                    suggestedName: filename,
                    types: [{
                        description: 'JSON File',
                        accept: { 'application/json': ['.json'] },
                    }],
                });
                // @ts-ignore
                const writable = await handle.createWritable();
                await writable.write(jsonString);
                await writable.close();
                return;
            }
        } catch (err: any) {
            // User cancelled
            if (err.name === 'AbortError') return;
            console.warn('Save As dialog failed, falling back to download:', err);
        }

        // Fallback for browsers not supporting File System Access API
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    // 클립보드 복사 함수
    const handleCopy = (text: string) => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">



            {/* Settings & Upload Area */}
            <div className="bg-white rounded-3xl p-8 shadow-sm border border-slate-100 transition-all duration-300">
                <div
                    className="flex items-center justify-between mb-0 cursor-pointer group"
                    onClick={() => setIsConfigOpen(!isConfigOpen)}
                >
                    <div className="flex items-center gap-4">
                        <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                            <span className="w-1 h-6 bg-indigo-500 rounded-full inline-block"></span>
                            Configuration
                        </h2>
                        {data && (
                            <div className="flex items-center gap-2 animate-in fade-in slide-in-from-left-2">
                                <button
                                    onClick={(e) => { e.stopPropagation(); handleSaveJson(); }}
                                    className="px-3 py-1 rounded-lg text-[11px] font-bold flex items-center gap-1.5 transition-all bg-slate-900 text-white hover:bg-slate-800 shadow-sm"
                                    title="분석 결과 JSON 저장"
                                >
                                    <Download size={12} />
                                    Save Result
                                </button>
                                <button
                                    onClick={(e) => { e.stopPropagation(); setIsDiffModalOpen(true); }}
                                    className="px-3 py-1 rounded-lg text-[11px] font-bold flex items-center gap-1.5 transition-all bg-white text-indigo-600 border border-indigo-200 hover:bg-indigo-50 shadow-sm"
                                    title="레코드 누락 확인 (Diff)"
                                >
                                    <GitCompare size={12} />
                                    Diff
                                </button>
                            </div>
                        )}
                    </div>
                    <ChevronRight
                        size={20}
                        className={cn("text-slate-400 transition-transform duration-300 group-hover:text-indigo-500", isConfigOpen ? "rotate-90" : "")}
                    />
                </div>

                <div className={cn("grid grid-cols-1 lg:grid-cols-4 gap-8 overflow-hidden transition-all duration-500 ease-in-out", isConfigOpen ? "mt-8 max-h-[500px] opacity-100" : "max-h-0 opacity-0")}>
                    {/* Mode Switcher */}
                    <div className="lg:col-span-4 flex gap-4 border-b border-slate-100 pb-4">
                        <button
                            onClick={(e) => { e.stopPropagation(); setIsAutoMode(true); }}
                            className={cn("px-4 py-2 font-bold rounded-lg text-sm transition-all shadow-sm", isAutoMode ? "bg-indigo-600 text-white" : "bg-white border text-slate-500 hover:bg-slate-50")}
                        >
                            Auto Load
                        </button>
                        <button
                            onClick={(e) => { e.stopPropagation(); setIsAutoMode(false); }}
                            className={cn("px-4 py-2 font-bold rounded-lg text-sm transition-all shadow-sm", !isAutoMode ? "bg-indigo-600 text-white" : "bg-white border text-slate-500 hover:bg-slate-50")}
                        >
                            Manual Upload
                        </button>
                    </div>

                    {/* Sheet Name Input */}
                    <div className="lg:col-span-1 space-y-2">
                        <label className="text-sm font-semibold text-slate-700">Target Sheet</label>
                        <input
                            type="text"
                            value={sheetName}
                            onChange={(e) => setSheetName(e.target.value)}
                            onClick={(e) => e.stopPropagation()}
                            className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:bg-white outline-none transition-all"
                            placeholder="e.g. Sheet1"
                        />
                        <p className="text-[11px] text-slate-400 pl-1">Name of the sheet to analyze</p>
                    </div>

                    {/* File Inputs or Auto Inputs */}
                    <div className="lg:col-span-2 grid grid-cols-2 gap-4">
                        {isAutoMode ? (
                            <>
                                <div className="space-y-2">
                                    <label className="text-sm font-semibold text-slate-700">Date (YYYYMMDD)</label>
                                    <input
                                        type="text"
                                        value={autoDate}
                                        onChange={(e) => setAutoDate(e.target.value)}
                                        onClick={(e) => e.stopPropagation()}
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:bg-white outline-none transition-all"
                                        placeholder="e.g. 20260101"
                                    />
                                    <p className="text-[11px] text-slate-400 pl-1">Target test split date</p>
                                </div>
                                <div className="space-y-2">
                                    <label className="text-sm font-semibold text-slate-700">Type</label>
                                    <select
                                        value={autoType}
                                        onChange={(e) => setAutoType(e.target.value)}
                                        onClick={(e) => e.stopPropagation()}
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:bg-white outline-none transition-all"
                                    >
                                        <option value="A">Type A</option>
                                        <option value="B">Type B</option>
                                        <option value="C">Type C</option>
                                    </select>
                                    <p className="text-[11px] text-slate-400 pl-1">Target test split delimiter</p>
                                </div>
                            </>
                        ) : (
                            <>
                                <FileInput
                                    label="Human (Ground Truth)"
                                    file={humanFile}
                                    onChange={(e) => handleFileChange(e, setHumanFile)}
                                />
                                <FileInput
                                    label="AI (Prediction)"
                                    file={llmFile}
                                    onChange={(e) => handleFileChange(e, setLlmFile)}
                                />
                            </>
                        )}
                    </div>

                    {/* Action Button */}
                    <div className="lg:col-span-1 flex items-end">
                        <button
                            onClick={(e) => { e.stopPropagation(); handleCompare(); }}
                            disabled={loading}
                            className="w-full h-[88px] bg-slate-900 hover:bg-slate-800 text-white rounded-2xl font-bold text-lg transition-all shadow-xl shadow-slate-200 disabled:opacity-70 disabled:shadow-none flex flex-col items-center justify-center gap-2"
                        >
                            {loading ? (
                                <>
                                    <RefreshCw className="animate-spin" />
                                    <span className="text-sm font-normal">Processing...</span>
                                </>
                            ) : (
                                <>
                                    <span className="flex items-center gap-2">Analyze <ChevronRight size={20} /></span>
                                    <span className="text-xs font-normal text-slate-400">Start Comparison</span>
                                </>
                            )}
                        </button>
                    </div>
                </div>

                {error && isConfigOpen && (
                    <div className="mt-6 p-4 bg-red-50 text-red-700 rounded-xl border border-red-100 flex items-start gap-3 animate-in fade-in slide-in-from-top-2">
                        <AlertCircle size={20} className="mt-0.5" />
                        <div className="text-sm font-medium">{error}</div>
                    </div>
                )}

                {/* Summary State when Closed */}
                {!isConfigOpen && data && (
                    <div className="mt-2 text-sm text-slate-500 pl-3 flex items-center gap-4 animate-in fade-in">
                        <span className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-indigo-500"></span>
                            Sheet: <span className="font-medium text-slate-700">{sheetName}</span>
                        </span>
                        <span className="w-1 h-1 rounded-full bg-slate-300"></span>
                        <span className="flex items-center gap-2">
                            <FileSpreadsheet size={14} />
                            Data: <span className="font-medium text-slate-700">{data.summary.total_human} rows</span>
                        </span>
                    </div>
                )}
            </div>

            {data && (
                <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 space-y-8">

                    {/* Workload Comparison Section */}
                    <div>
                        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                            <FileSpreadsheet size={16} /> Workload Statistics
                        </h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            {/* Human Stats */}
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 flex flex-col md:flex-row items-center justify-between gap-6 shadow-sm">
                                <div className="flex items-center gap-4">
                                    <div className="w-12 h-12 rounded-full bg-indigo-50 flex items-center justify-center text-indigo-600">
                                        <span className="font-bold text-lg">H</span>
                                    </div>
                                    <div>
                                        <p className="text-sm font-bold text-slate-500">Human (Ground Truth)</p>
                                        <p className="text-2xl font-extrabold text-slate-800">{data.summary.total_human.toLocaleString()} <span className="text-xs font-medium text-slate-400">msgs</span></p>
                                    </div>
                                </div>
                                <div className="flex gap-8 text-right">
                                    <div>
                                        <p className="text-xs font-bold text-slate-400 uppercase">Spam Count</p>
                                        <p className="text-lg font-bold text-rose-600">{data.summary.human_spam_count.toLocaleString()}</p>
                                    </div>
                                    <div>
                                        <p className="text-xs font-bold text-slate-400 uppercase">Spam Rate</p>
                                        <p className="text-lg font-bold text-slate-700">{(data.summary.human_spam_rate * 100).toFixed(1)}%</p>
                                    </div>
                                </div>
                            </div>

                            {/* AI Stats */}
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 flex flex-col md:flex-row items-center justify-between gap-6 shadow-sm">
                                <div className="flex items-center gap-4">
                                    <div className="w-12 h-12 rounded-full bg-violet-50 flex items-center justify-center text-violet-600">
                                        <span className="font-bold text-lg">AI</span>
                                    </div>
                                    <div>
                                        <p className="text-sm font-bold text-slate-500">AI Model</p>
                                        <p className="text-2xl font-extrabold text-slate-800">{data.summary.total_llm.toLocaleString()} <span className="text-xs font-medium text-slate-400">msgs</span></p>
                                    </div>
                                </div>
                                <div className="flex gap-8 text-right">
                                    <div>
                                        <p className="text-xs font-bold text-slate-400 uppercase">Spam Count</p>
                                        <p className="text-lg font-bold text-rose-600">{data.summary.llm_spam_count.toLocaleString()}</p>
                                    </div>
                                    <div>
                                        <p className="text-xs font-bold text-slate-400 uppercase">Spam Rate</p>
                                        <p className="text-lg font-bold text-slate-700">{(data.summary.llm_spam_rate * 100).toFixed(1)}%</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="w-full border-t border-slate-100"></div>

                    {/* 주요 지표: Accuracy + Kappa 듀얼 카드 */}
                    <div className="bg-gradient-to-br from-indigo-50 to-violet-50 rounded-3xl p-8 border-2 border-indigo-200 shadow-lg relative group">
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-6">
                            {/* Accuracy */}
                            <div className="flex-1">
                                <p className="text-xs font-bold uppercase tracking-widest text-indigo-600 mb-1 flex items-center gap-2">
                                    Accuracy (일치율)
                                    <AlertCircle size={12} className="text-indigo-400 cursor-help" />
                                </p>
                                <div className="flex items-baseline gap-2">
                                    <span className="text-5xl font-extrabold text-slate-900">
                                        {(data.summary.accuracy * 100).toFixed(1)}
                                    </span>
                                    <span className="text-lg text-slate-500 font-semibold">%</span>
                                </div>
                                <p className="text-xs text-slate-500 mt-1">Human-AI 전체 일치율</p>
                            </div>

                            {/* Divider */}
                            <div className="hidden md:block w-px h-20 bg-indigo-200"></div>

                            {/* Kappa */}
                            <div className="flex-1">
                                <p className="text-xs font-bold uppercase tracking-widest text-violet-600 mb-1 flex items-center gap-2">
                                    Cohen's Kappa (κ)
                                    <AlertCircle size={12} className="text-violet-400 cursor-help" />
                                </p>
                                <div className="flex items-baseline gap-2">
                                    <span className="text-5xl font-extrabold text-slate-900">
                                        {data.summary.kappa.toFixed(3)}
                                    </span>
                                </div>
                                <p className="text-xs text-slate-500 mt-1">{data.summary.kappa_status} (우연 제외)</p>
                            </div>

                            {/* Status Badge */}
                            <div className={cn(
                                "px-6 py-4 rounded-2xl font-bold text-lg shadow-lg text-center min-w-[160px]",
                                data.summary.primary_color === 'success' ? "bg-emerald-500 text-white" :
                                    data.summary.primary_color === 'warning' ? "bg-amber-500 text-white" :
                                        "bg-rose-500 text-white"
                            )}>
                                {data.summary.primary_status === '협업 가능' ? '🟢 협업 가능' :
                                    data.summary.primary_status === '모니터링 필요' ? '🟡 모니터링 필요' :
                                        '🔴 개선 필요'}
                            </div>
                        </div>

                        <p className="text-sm text-slate-600 leading-relaxed">
                            {data.summary.primary_description}
                        </p>

                        {/* Tooltip */}
                        <div className="absolute top-full left-1/2 -translate-x-1/2 mt-3 w-[420px] p-4 bg-slate-900 text-white text-xs rounded-2xl shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 pointer-events-none border border-slate-700">
                            <div className="absolute -top-2 left-1/2 -translate-x-1/2 w-3 h-3 bg-slate-900 rotate-45 border-t border-l border-slate-700"></div>

                            {/* Why these metrics */}
                            <div className="mb-4">
                                <p className="text-[10px] uppercase font-bold text-indigo-400 mb-2">왜 Accuracy + Kappa인가?</p>
                                <div className="space-y-1 text-slate-300 leading-relaxed">
                                    <p>• <strong>Accuracy</strong>: 직관적인 전체 일치율</p>
                                    <p>• <strong>Kappa</strong>: 우연 일치를 제외한 실질적 합의도</p>
                                    <p>• 두 지표 조합으로 과장 없는 객관적 평가 가능</p>
                                </div>
                            </div>

                            {/* Cohen's Kappa Explanation */}
                            <div className="mb-4 p-3 bg-slate-800 rounded-lg">
                                <p className="text-[10px] uppercase font-bold text-violet-400 mb-2">Cohen's Kappa (κ) 란?</p>
                                <div className="space-y-2 text-slate-300 leading-relaxed">
                                    <p>두 평가자 간 일치도를 측정하되, <strong className="text-white">우연히 일치할 확률을 제외</strong>한 지표입니다.</p>
                                    <div className="bg-slate-700 rounded px-2 py-1 font-mono text-[10px] text-center">
                                        κ = (Po - Pe) / (1 - Pe)
                                    </div>
                                    <div className="text-[10px] text-slate-400">
                                        <p>• Po = 실제 일치율 (Accuracy)</p>
                                        <p>• Pe = 우연에 의한 기대 일치율</p>
                                    </div>
                                </div>
                                <div className="mt-2 pt-2 border-t border-slate-700">
                                    <p className="text-[10px] font-bold text-slate-400 mb-1">Kappa 해석 기준 (Fleiss)</p>
                                    <div className="grid grid-cols-2 gap-1 text-[10px]">
                                        <span>≥0.75: 우수한 일치</span>
                                        <span>0.40~0.59: 중간 수준</span>
                                        <span>0.60~0.74: 상당한 일치</span>
                                        <span>&lt;0.40: 미흡</span>
                                    </div>
                                </div>
                            </div>

                            {/* Judgment Criteria */}
                            <div>
                                <p className="text-[10px] uppercase font-bold text-indigo-400 mb-2">종합 판정 기준</p>
                                <div className="space-y-1.5">
                                    <div className="flex items-center justify-between bg-emerald-900/30 rounded-lg px-3 py-1.5">
                                        <span className="font-mono text-[10px]">Acc ≥95% & κ ≥0.60</span>
                                        <span className="font-semibold text-emerald-400">🟢 협업 가능</span>
                                    </div>
                                    <div className="flex items-center justify-between bg-amber-900/30 rounded-lg px-3 py-1.5">
                                        <span className="font-mono text-[10px]">Acc ≥90% & κ ≥0.40</span>
                                        <span className="font-semibold text-amber-400">🟡 모니터링 필요</span>
                                    </div>
                                    <div className="flex items-center justify-between bg-rose-900/30 rounded-lg px-3 py-1.5">
                                        <span className="font-mono text-[10px]">그 외</span>
                                        <span className="font-semibold text-rose-400">🔴 개선 필요</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Human-LLM 합의도 섹션 (보조 지표) */}
                    <div>
                        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                            <BarChart3 size={16} /> 보조 지표
                        </h3>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <StatCard
                                title="MCC"
                                value={data.summary.mcc.toFixed(3)}
                                description="클래스 불균형에 강건한 상관계수 • ≥0.70 강함 • 0.50~0.70 중간 • <0.50 개선필요"
                            />
                            <StatCard
                                title="불일치율"
                                value={`${(data.summary.disagreement_rate * 100).toFixed(1)}%`}
                                subValue={`${data.summary.fp + data.summary.fn} 건`}
                                type={data.summary.disagreement_rate < 0.05 ? "success" : data.summary.disagreement_rate < 0.1 ? "warning" : "danger"}
                                description="전체 판단 중 Human-AI 불일치 비율 (FP + FN)"
                            />
                            <StatCard
                                title="일치 건수"
                                value={`${data.summary.tp + data.summary.tn}`}
                                subValue={`/ ${data.summary.tp + data.summary.tn + data.summary.fp + data.summary.fn} 건`}
                                type="success"
                                description="Accuracy 산출 기준: (TP + TN) / Total. Human-AI가 동일하게 판정한 건수입니다."
                            />
                            <StatCard
                                title="원본 매치율"
                                value={`${(data.summary.match_rate * 100).toFixed(1)}%`}
                                subValue="(참고용)"
                                type="neutral"
                                description="업로드된 두 파일 간 메시지 매칭 비율. 성능 지표가 아닌 데이터 정합성 참고용입니다."
                            />
                        </div>
                    </div>

                    <div className="w-full border-t border-slate-100"></div>

                    {/* Performance Metrics Grid (참고용 - Ground Truth 전제) */}
                    <div>
                        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                            <BarChart3 size={16} /> 스팸 탐지 성능 (참고용)
                        </h3>
                        <p className="text-xs text-slate-400 mb-4 -mt-2">※ Ground Truth를 정답으로 가정한 참고 지표입니다.</p>
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                            <StatCard
                                title="F1 Score"
                                value={data.summary.f1.toFixed(3)}
                                type="neutral"
                                description="Precision과 Recall의 조화 평균. Ground Truth 전제 하의 참고 지표입니다."
                            />
                            <StatCard
                                title="Precision"
                                value={data.summary.precision.toFixed(3)}
                                description="AI가 스팸이라고 분류한 것 중 Human도 스팸으로 판정한 비율입니다."
                            />
                            <StatCard
                                title="Recall"
                                value={data.summary.recall.toFixed(3)}
                                description="Human이 스팸으로 판정한 것 중 AI도 스팸으로 분류한 비율입니다."
                            />
                            <StatCard
                                title="Missed (FN)"
                                value={data.summary.fn}
                                type={data.summary.fn > 0 ? "danger" : "neutral"}
                                description="Human=SPAM, AI=HAM인 케이스. Human 오류일 가능성도 있습니다."
                            />
                            <StatCard
                                title="False Alarm (FP)"
                                value={data.summary.fp}
                                type={data.summary.fp > 0 ? "warning" : "neutral"}
                                description="Human=HAM, AI=SPAM인 케이스. AI가 맞을 가능성도 있습니다."
                            />
                        </div>
                    </div>

                    {/* 자동 생성 요약문 */}
                    <div className="bg-white rounded-3xl p-8 shadow-sm border border-slate-100">
                        <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
                            <span className="w-1 h-6 bg-indigo-500 rounded-full inline-block"></span>
                            분석 요약
                        </h3>
                        <div className="prose prose-sm max-w-none text-slate-700 leading-relaxed">
                            {data.auto_summary.split('\n\n').map((para, i) => (
                                <p key={i} className="mb-3">{para}</p>
                            ))}
                        </div>
                    </div>

                    {/* Split View */}
                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[700px]">

                        {/* List View */}
                        <div className="lg:col-span-4 bg-white border border-slate-200 rounded-2xl flex flex-col shadow-sm overflow-hidden">
                            <div className="p-4 border-b border-slate-100 bg-slate-50/50 backdrop-blur-sm space-y-3 sticky top-0">
                                <div className="flex items-center justify-between">
                                    <h3 className="font-bold text-slate-700">Mismatches</h3>
                                    <div className={cn(
                                        "px-2 py-1 rounded-md text-xs font-bold",
                                        filter === 'ALL' ? "bg-slate-200 text-slate-600" :
                                            filter === 'FN' ? "bg-rose-100 text-rose-700" :
                                                "bg-amber-100 text-amber-700"
                                    )}>
                                        {filter} {diffCounts[filter]}
                                    </div>
                                </div>

                                {/* Search */}
                                <div className="relative group">
                                    <Search className="absolute left-3 top-2.5 text-slate-400 group-focus-within:text-indigo-500 transition-colors" size={16} />
                                    <input
                                        type="text"
                                        placeholder="Search content..."
                                        value={searchTerm}
                                        onChange={e => setSearchTerm(e.target.value)}
                                        className="w-full pl-9 pr-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500 outline-none transition-all"
                                    />
                                </div>

                                {/* Filters */}
                                <div className="flex p-1 bg-slate-100 rounded-lg">
                                    {(['ALL', 'FN', 'FP'] as const).map((f) => (
                                        <button
                                            key={f}
                                            onClick={() => setFilter(f)}
                                            className={cn(
                                                "flex-1 py-1.5 px-2 rounded-md text-xs font-bold transition-all flex items-center justify-center gap-1",
                                                filter === f
                                                    ? "bg-white text-slate-800 shadow-sm"
                                                    : "text-slate-500 hover:text-slate-700"
                                            )}
                                        >
                                            {f}
                                            <span className={cn(
                                                "text-[10px] px-1.5 py-0.5 rounded-full",
                                                filter === f
                                                    ? f === 'FN' ? "bg-rose-100 text-rose-700"
                                                        : f === 'FP' ? "bg-amber-100 text-amber-700"
                                                            : "bg-slate-200 text-slate-600"
                                                    : "bg-slate-200/50 text-slate-400"
                                            )}>
                                                {diffCounts[f]}
                                            </span>
                                        </button>
                                    ))}
                                </div>

                                {/* Download Buttons */}
                                <div className="flex gap-1">
                                    {(['ALL', 'FN', 'FP'] as const).map((f) => (
                                        <button
                                            key={`download-${f}`}
                                            onClick={() => handleDownloadText(f)}
                                            className={cn(
                                                "flex-1 py-1.5 px-2 rounded-lg text-[10px] font-bold transition-all flex items-center justify-center gap-1 border",
                                                f === 'ALL'
                                                    ? "bg-slate-700 text-white hover:bg-slate-800 border-slate-700"
                                                    : f === 'FN'
                                                        ? "bg-rose-50 text-rose-700 hover:bg-rose-100 border-rose-200"
                                                        : "bg-amber-50 text-amber-700 hover:bg-amber-100 border-amber-200"
                                            )}
                                            title={`${f} 항목 텍스트 다운로드`}
                                        >
                                            <Download size={10} />
                                            {f}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
                                {filteredDiffs?.length === 0 && (
                                    <div className="h-full flex flex-col items-center justify-center text-slate-400">
                                        <Search size={32} className="opacity-20 mb-2" />
                                        <span className="text-sm">No items match</span>
                                    </div>
                                )}
                                {filteredDiffs?.map(diff => (
                                    <div
                                        key={diff.diff_id}
                                        onClick={() => setSelectedDiff(diff)}
                                        className={cn(
                                            "p-3 rounded-xl cursor-pointer border transition-all text-left group",
                                            selectedDiff?.diff_id === diff.diff_id
                                                ? "bg-indigo-50 border-indigo-200 ring-1 ring-indigo-200 shadow-sm"
                                                : "bg-white border-transparent hover:bg-slate-50 hover:border-slate-200"
                                        )}
                                    >
                                        <div className="flex items-center justify-between mb-2">
                                            <span className={cn(
                                                "px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide border",
                                                diff.diff_type === 'FN'
                                                    ? "bg-rose-50 text-rose-700 border-rose-100"
                                                    : "bg-amber-50 text-amber-700 border-amber-100"
                                            )}>
                                                {diff.diff_type === 'FN' ? 'Missed (FN)' : 'False Alarm (FP)'}
                                            </span>
                                            <span className="text-[10px] text-slate-400 font-mono">#{diff.diff_id.slice(0, 4)}</span>
                                        </div>
                                        <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed group-hover:text-slate-900">
                                            {diff.message_preview}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Detail View */}
                        <div className="lg:col-span-8 bg-white border border-slate-200 rounded-2xl p-6 shadow-sm overflow-hidden flex flex-col h-full">
                            {selectedDiff ? (
                                <div className="h-full flex flex-col">
                                    <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-100">
                                        <div>
                                            <span className={cn(
                                                "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide border",
                                                selectedDiff.diff_type === 'FN'
                                                    ? "bg-rose-50 text-rose-700 border-rose-100"
                                                    : "bg-amber-50 text-amber-700 border-amber-100"
                                            )}>
                                                {selectedDiff.diff_type} Case
                                            </span>
                                            <h4 className="font-bold text-lg text-slate-900 mt-2">Detail Analysis</h4>
                                            <p className="text-xs text-slate-400 font-mono mt-1">ID: {selectedDiff.diff_id}</p>
                                        </div>

                                        {/* RAG 등록 버튼 */}
                                        <button
                                            onClick={() => handleOpenRagModal(selectedDiff)}
                                            className="px-3 py-2 bg-indigo-50 text-indigo-700 text-xs font-bold rounded-lg hover:bg-indigo-100 flex items-center gap-1.5 transition-colors"
                                        >
                                            <Database size={14} />
                                            RAG 등록
                                        </button>
                                    </div>

                                    <div className="flex-1 overflow-y-auto space-y-6 custom-scrollbar pr-2">
                                        {/* Message Content */}
                                        <div className="bg-slate-50 p-5 rounded-xl border border-slate-200">
                                            <div className="flex items-center justify-between mb-3">
                                                <h5 className="text-xs font-bold text-slate-500 uppercase tracking-widest">Message Content</h5>
                                                <button
                                                    onClick={() => handleCopy(selectedDiff.message_full)}
                                                    className={cn(
                                                        "p-1.5 rounded-lg transition-all flex items-center gap-1.5 text-[10px] font-bold",
                                                        copied ? "bg-emerald-100 text-emerald-700" : "bg-white text-slate-500 hover:text-indigo-600 border border-slate-200 shadow-sm"
                                                    )}
                                                >
                                                    {copied ? (
                                                        <>
                                                            <Check size={12} />
                                                            Copied!
                                                        </>
                                                    ) : (
                                                        <>
                                                            <Copy size={12} />
                                                            Copy
                                                        </>
                                                    )}
                                                </button>
                                            </div>
                                            <p className="text-sm text-slate-800 whitespace-pre-wrap leading-relaxed font-medium">
                                                {selectedDiff.message_full}
                                            </p>
                                        </div>

                                        {/* Comparison Grid */}
                                        <div className="grid grid-cols-2 gap-4">
                                            {/* Human */}
                                            <div className="border border-slate-200 rounded-xl p-4 relative overflow-hidden">
                                                <div className={cn("absolute top-0 left-0 w-1 h-full", selectedDiff.human_is_spam ? "bg-rose-500" : "bg-emerald-500")}></div>
                                                <h5 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3 flex items-center gap-2">
                                                    <span className="w-4 h-4 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 text-[10px]">H</span>
                                                    Human Decision
                                                </h5>
                                                <div className="space-y-3">
                                                    <div>
                                                        <span className={cn(
                                                            "text-sm font-bold px-2 py-1 rounded-md",
                                                            selectedDiff.human_is_spam ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"
                                                        )}>
                                                            {selectedDiff.human_is_spam ? "SPAM" : "HAM"}
                                                        </span>
                                                    </div>
                                                    {selectedDiff.human_code && (
                                                        <div className="text-xs text-slate-600">
                                                            <span className="font-semibold text-slate-400">Code:</span> {selectedDiff.human_code}
                                                        </div>
                                                    )}
                                                    {selectedDiff.human_reason && (
                                                        <div className="text-xs text-slate-600 bg-slate-50 p-2 rounded-lg">
                                                            {selectedDiff.human_reason}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>

                                            {/* LLM */}
                                            <div className="border border-slate-200 rounded-xl p-4 relative overflow-hidden">
                                                <div className={cn("absolute top-0 left-0 w-1 h-full", selectedDiff.llm_is_spam ? "bg-rose-500" : "bg-emerald-500")}></div>
                                                <h5 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3 flex items-center gap-2">
                                                    <span className="w-4 h-4 rounded-full bg-violet-100 flex items-center justify-center text-violet-600 text-[10px]">AI</span>
                                                    AI Decision
                                                </h5>
                                                <div className="space-y-3">
                                                    <div>
                                                        <span className={cn(
                                                            "text-sm font-bold px-2 py-1 rounded-md",
                                                            selectedDiff.llm_is_spam ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"
                                                        )}>
                                                            {selectedDiff.llm_is_spam ? "SPAM" : "HAM"}
                                                        </span>
                                                    </div>
                                                    {selectedDiff.llm_code && (
                                                        <div className="text-xs text-slate-600">
                                                            <span className="font-semibold text-slate-400">Code:</span> {selectedDiff.llm_code}
                                                        </div>
                                                    )}
                                                    {/* Policy Interpretation */}
                                                    {selectedDiff.policy_interpretation && (
                                                        <div className="inline-block px-2 py-1 bg-violet-50 text-violet-700 text-[10px] font-bold rounded-full border border-violet-100 mb-2">
                                                            {selectedDiff.policy_interpretation}
                                                        </div>
                                                    )}
                                                    {selectedDiff.llm_reason && (
                                                        <div className="text-xs text-slate-600 bg-slate-50 p-2 rounded-lg leading-relaxed">
                                                            {selectedDiff.llm_reason}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div className="h-full flex flex-col items-center justify-center text-slate-400">
                                    <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mb-4">
                                        <BarChart3 size={32} className="opacity-20" />
                                    </div>
                                    <p className="font-medium">Select a mismatch item to view details</p>
                                    <p className="text-sm opacity-60 mt-1">Click on the list to the left</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* RAG Registration Modal */}
            <RagRegistrationModal
                isOpen={isRagModalOpen}
                onClose={() => setIsRagModalOpen(false)}
                data={ragModalData}
                onSave={handleSaveToRag}
            />

            {/* RAG Save Toast */}
            {ragSaveStatus !== 'idle' && (
                <div className={cn(
                    "fixed bottom-8 right-8 px-6 py-4 rounded-xl shadow-2xl flex items-center gap-3 transition-all transform z-50",
                    ragSaveStatus === 'success' ? "bg-slate-900 text-white translate-y-0 opacity-100" : "translate-y-10 opacity-0"
                )}>
                    <div className="w-6 h-6 rounded-full bg-emerald-500 flex items-center justify-center text-slate-900">
                        <Check size={14} strokeWidth={3} />
                    </div>
                    <span className="font-bold text-sm tracking-wide">{ragSaveMessage}</span>
                </div>
            )}

            {/* Record Diff Modal */}
            {isDiffModalOpen && data && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
                    <div className="bg-white w-full max-w-5xl max-h-[90vh] rounded-3xl shadow-2xl overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
                        {/* Header */}
                        <div className="px-8 py-6 border-b flex items-center justify-between bg-gray-50/50">
                            <div>
                                <div className="flex items-center gap-2">
                                    <h3 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                                        <GitCompare className="text-indigo-600" size={24} />
                                        Record Comparison Diff
                                    </h3>
                                </div>
                                <p className="text-sm text-gray-500 mt-1">
                                    두 엑셀 파일 간의 레코드 일치 여부를 확인합니다. (메시지 원문 및 순번 기준)
                                </p>
                            </div>
                            <button
                                onClick={() => setIsDiffModalOpen(false)}
                                className="p-2 hover:bg-gray-200 rounded-full transition-colors"
                            >
                                <X size={24} className="text-gray-500" />
                            </button>
                        </div>

                        {/* Content */}
                        <div className="flex-1 overflow-auto p-8 grid grid-cols-2 gap-8 bg-slate-50/30">
                            {/* Missing in LLM (Only in Human) */}
                            <div className="space-y-4">
                                <div className="flex items-center justify-between">
                                    <h4 className="font-bold text-amber-700 flex items-center gap-2 bg-amber-50 px-3 py-1.5 rounded-lg border border-amber-100">
                                        <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                                        In Human Only ({(data.missing_in_llm || []).length})
                                    </h4>
                                </div>
                                <div className="space-y-3">
                                    {(!data.missing_in_llm || data.missing_in_llm.length === 0) ? (
                                        <div className="py-20 text-center text-gray-400 bg-white rounded-2xl border border-dashed border-gray-200">
                                            누락된 레코드가 없습니다.
                                        </div>
                                    ) : (
                                        <div className="grid gap-3">
                                            {(data.missing_in_llm || []).map((rec, idx) => (
                                                <div key={idx} className="p-4 rounded-xl border border-gray-200 bg-white hover:border-amber-200 transition-all shadow-sm group">
                                                    <div className="flex items-start justify-between gap-2 mb-2">
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-[10px] font-bold text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded uppercase tracking-tighter">Human Excel</span>
                                                            <span className="text-[10px] font-bold text-indigo-400">Row {rec.index + 1}</span>
                                                        </div>
                                                        <span className={cn(
                                                            "text-[9px] font-bold px-1.5 py-0.5 rounded-full border uppercase",
                                                            rec.label === 'o' ? "bg-rose-50 text-rose-600 border-rose-100" : "bg-emerald-50 text-emerald-600 border-emerald-100"
                                                        )}>
                                                            {rec.label === 'o' ? 'SPAM' : 'HAM'}
                                                        </span>
                                                    </div>
                                                    <p className="text-sm text-gray-700 font-medium line-clamp-4 leading-relaxed group-hover:text-gray-900">{rec.message}</p>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Missing in Human (Only in LLM) */}
                            <div className="space-y-4">
                                <div className="flex items-center justify-between">
                                    <h4 className="font-bold text-violet-700 flex items-center gap-2 bg-violet-50 px-3 py-1.5 rounded-lg border border-violet-100">
                                        <span className="w-2 h-2 rounded-full bg-violet-500 animate-pulse" />
                                        In LLM Only ({(data.missing_in_human || []).length})
                                    </h4>
                                </div>
                                <div className="space-y-3">
                                    {(!data.missing_in_human || data.missing_in_human.length === 0) ? (
                                        <div className="py-20 text-center text-gray-400 bg-white rounded-2xl border border-dashed border-gray-200">
                                            누락된 레코드가 없습니다.
                                        </div>
                                    ) : (
                                        <div className="grid gap-3">
                                            {(data.missing_in_human || []).map((rec, idx) => (
                                                <div key={idx} className="p-4 rounded-xl border border-gray-200 bg-white hover:border-violet-200 transition-all shadow-sm group">
                                                    <div className="flex items-start justify-between gap-2 mb-2">
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-[10px] font-bold text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded uppercase tracking-tighter">LLM Excel</span>
                                                            <span className="text-[10px] font-bold text-indigo-400">Row {rec.index + 1}</span>
                                                        </div>
                                                        <span className={cn(
                                                            "text-[9px] font-bold px-1.5 py-0.5 rounded-full border uppercase",
                                                            rec.label === 'o' ? "bg-rose-50 text-rose-600 border-rose-100" : "bg-emerald-50 text-emerald-600 border-emerald-100"
                                                        )}>
                                                            {rec.label === 'o' ? 'SPAM' : 'HAM'}
                                                        </span>
                                                    </div>
                                                    <p className="text-sm text-gray-700 font-medium line-clamp-4 leading-relaxed group-hover:text-gray-900">{rec.message}</p>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Footer */}
                        <div className="p-6 bg-gray-50 border-t flex justify-between items-center px-8 text-xs text-gray-400 italic">
                            <p>* '메시지 내용'과 '동일 메시지의 출현 순서'가 일치하지 않는 경우 차이로 인식됩니다.</p>
                            <button
                                onClick={() => setIsDiffModalOpen(false)}
                                className="px-8 py-3 bg-slate-900 text-white rounded-2xl font-bold hover:bg-slate-800 transition-all shadow-lg active:scale-95"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </main>
    );
}
