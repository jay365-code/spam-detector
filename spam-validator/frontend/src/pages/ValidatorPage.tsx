import React, { useState, useRef } from 'react';
import axios from 'axios';
import { Upload, FileSpreadsheet, RefreshCw, AlertCircle, ChevronRight, ChevronUp, ChevronDown, BarChart3, Search, Download, Check, Database, Copy, GitCompare, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { RagRegistrationModal } from '../RagRegistrationModal';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// --- Utility ---
function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

const HighlightText = ({ text, highlight }: { text: string; highlight: string }) => {
    if (!highlight.trim() || !text) return <>{text}</>;
    const escapeRegExp = (str: string) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const parts = String(text).split(new RegExp(`(${escapeRegExp(highlight)})`, 'gi'));
    return (
        <React.Fragment>
            {parts.map((part, i) => 
                part.toLowerCase() === highlight.toLowerCase() ? (
                    <mark key={i} className="bg-yellow-200/80 text-slate-900 rounded-sm font-semibold">{part}</mark>
                ) : (
                    <span key={i}>{part}</span>
                )
            )}
        </React.Fragment>
    );    
};

const LinkifyText = ({ text }: { text: string }) => {
    if (!text) return null;
    const urlRegex = /(https?:\/\/[^\s]+)/g;
    const parts = text.split(urlRegex);
    return (
        <React.Fragment>
            {parts.map((part, i) => 
                part.match(urlRegex) ? (
                    <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:text-blue-600 hover:underline">
                        {part}
                    </a>
                ) : (
                    <span key={i}>{part}</span>
                )
            )}
        </React.Fragment>
    );    
};

// --- Types ---
interface SummaryMetrics {
    sheet_used: string;
    total_human: number;
    total_llm: number;
    type_b_total_count: number;
    type_b_url_count: number;
    type_b_sig_count: number;
    type_b_both_count: number;
    type_b_none_count: number;
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
    llm_semantic_class?: string;
    llm_url?: string;
    llm_message_extracted_url?: string;
    llm_signature?: string;
}

interface MissingRecord {
    index: number;
    message: string;
    label: string;
    code: string;
    reason: string;
}

interface TypeBItem {
    message_preview: string;
    message_full: string;
    semantic_class: string;
    llm_reason: string;
    llm_code: string;
    is_spam: boolean;
    extracted_url?: string;
    extracted_signature?: string;
}

interface TypeAItem {
    message_preview: string;
    message_full: string;
    semantic_class: string;
    llm_reason: string;
    llm_code: string;
    is_spam: boolean;
}

interface HumanBasedDiffItem {
    index: number;
    message_full: string;
    human_is_spam: boolean;
    human_code: string;
    human_reason: string;
    llm_is_spam: boolean | null;
    llm_code: string;
    llm_reason: string;
    llm_url: string;
    llm_message_extracted_url: string;
    llm_signature: string;
    match_status: "MATCH" | "FN" | "FP" | "MISSING_IN_LLM";
}

interface CompareResponse {
    summary: SummaryMetrics;
    diffs: DiffItem[];
    human_based_diffs: HumanBasedDiffItem[];
    type_b_items: TypeBItem[];
    type_a_items: TypeAItem[];
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
    
    // Diff Modal State (Integrated 1:1 Viewer)
    const [isDiffModalOpen, setIsDiffModalOpen] = useState(false);
    const [diffFilter, setDiffFilter] = useState<'ALL' | 'MATCH' | 'MISMATCH' | 'MISSING'>('ALL');
    const [diffSearchText, setDiffSearchText] = useState('');
    
    // Diff Table Expand/Collapse State
    const [expandedDiffs, setExpandedDiffs] = useState<Set<number>>(new Set());
    const toggleDiffExpand = (index: number) => {
        setExpandedDiffs(prev => {
            const next = new Set(prev);
            if (next.has(index)) next.delete(index);
            else next.add(index);
            return next;
        });
    };

    // Diff Table Resizable Columns State
    const [colWidths, setColWidths] = useState<{ [key: string]: number }>({
        row: 80,
        message: 400,
        human: 300,
        llm: 300,
        status: 120
    });
    const resizingCol = useRef<string | null>(null);
    const startX = useRef<number>(0);
    const startWidth = useRef<number>(0);

    const handleMouseDown = (e: React.MouseEvent, colKey: string) => {
        resizingCol.current = colKey;
        startX.current = e.clientX;
        startWidth.current = colWidths[colKey];
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
    };

    const handleMouseMove = (e: MouseEvent) => {
        if (!resizingCol.current) return;
        const diffX = e.clientX - startX.current;
        const newWidth = Math.max(100, startWidth.current + diffX); // 최소 100px 보장
        setColWidths(prev => ({ ...prev, [resizingCol.current as string]: newWidth }));
    };

    const handleMouseUp = () => {
        resizingCol.current = null;
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
    };

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


    // Summary Expanded State
    const [isSummaryExpanded, setIsSummaryExpanded] = useState(true);

    // Human Error (AI Correctness) State
    const [correctedIds, setCorrectedIds] = useState<Set<string>>(new Set());
    const [isCorrecting, setIsCorrecting] = useState<string | null>(null);

    // AI가 맞았음(Human Error) 처리 함수
    const handleMarkAsHumanError = async (diffId: string) => {
        setIsCorrecting(diffId);
        try {
            // TODO: 실제 백엔드 연동 API 호출
            // await axios.post('http://localhost:8001/api/human-error', { diff_id: diffId });
            
            // 시뮬레이션 지연
            await new Promise(resolve => setTimeout(resolve, 500));
            
            // 상태 업데이트
            setCorrectedIds(prev => {
                const next = new Set(prev);
                next.add(diffId);
                return next;
            });
        } catch (error) {
            console.error("Failed to mark as human error:", error);
            alert("처리 중 무언가 문제가 발생했습니다.");
        } finally {
            setIsCorrecting(null);
        }
    };

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
        if (!data) return;
        if (!isAutoMode && !humanFile) return;

        let filename = 'comparison_result.json';

        if (isAutoMode) {
            filename = `일별비교_${autoDate}_${autoType}.json`;
        } else if (humanFile) {
            // 파일명에서 날짜와 식별자 추출 (예: MMSC스팸추출_20260101_A.xlsx -> 20260101_A)
            const match = humanFile.name.match(/(\d{8})_([A-Z])/);
            if (match) {
                const [_, date, type] = match;
                filename = `일별비교_${date}_${type}.json`;
            }
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

    // Diff 결과를 Excel로 저장 (백엔드 경로에 저장)
    const handleSaveDiffExcel = async () => {
        if (!data) return;
        if (!data.human_based_diffs || data.human_based_diffs.length === 0) {
            alert("저장할 데이터가 없습니다.");
            return;
        }
        
        let filename = 'DIFF_result.xlsx';
        const todayDate = new Date().toISOString().slice(0, 10).replace(/-/g, '');
        
        if (isAutoMode && autoDate && autoType) {
            filename = `DIFF_${autoDate}_${autoType}.xlsx`;
        } else if (humanFile) {
            const match = humanFile.name.match(/(\d{8})_([A-Z])/);
            if (match) {
                filename = `DIFF_${match[1]}_${match[2]}.xlsx`;
            } else {
                filename = `DIFF_${todayDate}_A.xlsx`;
            }
        } else {
            filename = `DIFF_${todayDate}_A.xlsx`;
        }

        try {
            const response = await axios.post('http://localhost:8001/export/diff', {
                summary: data.summary,
                human_based_diffs: data.human_based_diffs,
                filename: filename
            });
            
            const openIt = window.confirm(`엑셀 파일이 성공적으로 지정된 폴더에 저장되었습니다:\n${response.data.path}\n\n지금 해당 파일을 바로 여시겠습니까?`);
            if (openIt) {
                try {
                    await axios.post('http://localhost:8001/export/open', { path: response.data.path });
                } catch (openErr) {
                    console.error("Failed to open file automatically:", openErr);
                    alert("파일 여는 중 오류가 발생했습니다. 직접 폴더에서 열어주세요.");
                }
            }
        } catch (error) {
            console.error('Failed to export diff excel:', error);
            alert('엑셀 저장 중 (서버) 오류가 발생했습니다.');
        }
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
                            <div className="bg-white border text-left border-slate-200 rounded-2xl p-6 flex flex-col items-start justify-between gap-4 shadow-sm">
                                <div className="flex items-center gap-4 w-full">
                                    <div className="w-12 h-12 rounded-full bg-violet-50 flex items-center justify-center text-violet-600 shrink-0">
                                        <span className="font-bold text-lg">AI</span>
                                    </div>
                                    <div className="flex-1">
                                        <p className="text-sm font-bold text-slate-500">AI Model</p>
                                        <p className="text-2xl font-extrabold text-slate-800">{data.summary.total_llm.toLocaleString()} <span className="text-xs font-medium text-slate-400">msgs</span></p>
                                    </div>
                                </div>
                                <div className="border-t border-slate-100 w-full pt-4 mt-2">
                                    <div className="flex justify-between items-end mb-3">
                                        <div>
                                            <p className="text-xs font-bold text-slate-400 uppercase">Total AI SPAM</p>
                                            <p className="text-2xl font-black text-rose-600 leading-none">
                                                {(data.summary.llm_spam_count).toLocaleString()} 
                                            </p>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-xs font-bold text-slate-400 uppercase">Spam Rate</p>
                                            <p className="text-lg font-bold text-slate-700">
                                                {((data.summary.llm_spam_count / data.summary.total_llm) * 100).toFixed(1)}%
                                            </p>
                                        </div>
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
                                title="사람이 놓친 스팸 (AI 검출)"
                                value={data.summary.fp}
                                type={data.summary.fp > 0 ? "warning" : "neutral"}
                                description="사람은 정상이지만 AI가 스팸으로 본 건 (유형 2 불일치). AI가 사람의 실수를 잡은 것(Human Error)일 수 있습니다."
                            />
                            {/* AI Error Corrected Card */}
                            <StatCard
                                title="AI 교정률 (Human Error)"
                                value={correctedIds.size}
                                subValue={`/ ${data.summary.fp + data.summary.fn}건`}
                                type={correctedIds.size > 0 ? "brand" : "neutral"}
                                description="불일치 건 중 AI의 판단이 맞았음(사람의 실수)으로 확인 및 교정된 건수입니다."
                            />
                        </div>
                    </div>

                    {/* 자동 생성 요약문 */}
                    <div className="bg-white rounded-3xl p-8 shadow-sm border border-slate-100 transition-all duration-300">
                        <div className="flex items-center justify-between mb-2">
                            <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                                <span className="w-1 h-6 bg-indigo-500 rounded-full inline-block"></span>
                                분석 요약
                            </h3>
                            <button
                                onClick={() => setIsSummaryExpanded(!isSummaryExpanded)}
                                className="p-1.5 hover:bg-slate-100 rounded-full transition-colors text-slate-500"
                            >
                                {isSummaryExpanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                            </button>
                        </div>
                        <div className={cn("grid transition-all duration-300 ease-in-out", isSummaryExpanded ? "grid-rows-[1fr] opacity-100 mt-2" : "grid-rows-[0fr] opacity-0 mt-0")}>
                            <div className="overflow-hidden">
                                <div className="prose prose-sm max-w-none text-slate-700 leading-relaxed whitespace-pre-wrap">
                                    <ReactMarkdown>{data.auto_summary.replace(/\*\*(.*?)\*\*(?=[가-힣])/g, '**$1** ')}</ReactMarkdown>
                                </div>
                            </div>
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
                                {filteredDiffs?.map(diff => {
                                    const isCorrected = correctedIds.has(diff.diff_id);
                                    return (
                                        <div
                                            key={diff.diff_id}
                                            onClick={() => setSelectedDiff(diff)}
                                            className={cn(
                                                "p-3 rounded-xl cursor-pointer border transition-all text-left group relative",
                                                selectedDiff?.diff_id === diff.diff_id
                                                    ? "bg-indigo-50 border-indigo-200 ring-1 ring-indigo-200 shadow-sm"
                                                    : "bg-white border-transparent hover:bg-slate-50 hover:border-slate-200"
                                            )}
                                        >
                                            <div className="flex items-center justify-between mb-2">
                                                <span className={cn(
                                                    "px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide border",
                                                    isCorrected 
                                                        ? "bg-emerald-50 text-emerald-700 border-emerald-100" 
                                                        : diff.diff_type === 'FN'
                                                            ? "bg-rose-50 text-rose-700 border-rose-100"
                                                            : "bg-amber-50 text-amber-700 border-amber-100"
                                                )}>
                                                    {isCorrected ? '✔ HUMAN ERROR' : (diff.diff_type === 'FN' ? '유형 1 (보수적 판단)' : '유형 2 (AI가 스팸 분류)')}
                                                </span>
                                                <span className="text-[10px] text-slate-400 font-mono">#{diff.diff_id.slice(0, 4)}</span>
                                            </div>
                                            <p className={cn("text-xs line-clamp-2 leading-relaxed group-hover:text-slate-900 break-all", isCorrected ? "text-slate-400" : "text-slate-600")}>
                                                {diff.message_preview}
                                            </p>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Detail View */}
                        <div className="lg:col-span-8 bg-white border border-slate-200 rounded-2xl p-6 shadow-sm overflow-hidden flex flex-col h-full">
                            {selectedDiff ? (
                                <div className="h-full flex flex-col">
                                    <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-100">
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <span className={cn(
                                                    "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide border",
                                                    correctedIds.has(selectedDiff.diff_id) 
                                                        ? "bg-emerald-50 text-emerald-700 border-emerald-100 shadow-sm shadow-emerald-100" 
                                                        : selectedDiff.diff_type === 'FN'
                                                            ? "bg-rose-50 text-rose-700 border-rose-100"
                                                            : "bg-amber-50 text-amber-700 border-amber-100"
                                                )}>
                                                    {correctedIds.has(selectedDiff.diff_id) ? "✔ HUMAN ERROR" : (selectedDiff.diff_type === 'FN' ? '유형 1 (보수적 판단)' : '유형 2 (AI가 스팸 분류)')}
                                                </span>
                                            </div>
                                            <h4 className="font-bold text-lg text-slate-900 mt-2">Detail Analysis</h4>
                                            <p className="text-xs text-slate-400 font-mono mt-1">ID: {selectedDiff.diff_id}</p>
                                        </div>

                                        <div className="flex gap-2">
                                            {/* Human Error Mark Button */}
                                            {!correctedIds.has(selectedDiff.diff_id) ? (
                                                <button 
                                                    onClick={() => handleMarkAsHumanError(selectedDiff.diff_id)}
                                                    disabled={isCorrecting === selectedDiff.diff_id}
                                                    className="px-3 py-2 rounded-lg text-xs font-bold transition-all shadow-sm flex items-center gap-1.5 bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
                                                >
                                                    {isCorrecting === selectedDiff.diff_id ? (
                                                        <RefreshCw size={14} className="animate-spin" />
                                                    ) : (
                                                        <Check size={14} />
                                                    )}
                                                    AI가 맞았음(Human Error)
                                                </button>
                                            ) : (
                                                <div className="px-3 py-2 rounded-lg text-xs font-bold shadow-sm flex items-center gap-1.5 bg-emerald-100 text-emerald-700 border border-emerald-200">
                                                    <Check size={14} /> 교정 완료됨
                                                </div>
                                            )}
                                            {/* RAG 등록 버튼 */}
                                            <button
                                                onClick={() => handleOpenRagModal(selectedDiff)}
                                                className="px-3 py-2 bg-indigo-50 text-indigo-700 text-xs font-bold rounded-lg hover:bg-indigo-100 flex items-center gap-1.5 transition-colors"
                                            >
                                                <Database size={14} />
                                                RAG 등록
                                            </button>
                                        </div>
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
                                                <LinkifyText text={selectedDiff.message_full} />
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
                                                    <div className="flex items-center gap-2 flex-wrap">
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
                                                        <div className="text-xs text-slate-600 bg-slate-50 p-2 rounded-lg leading-relaxed break-words whitespace-pre-wrap">
                                                            {selectedDiff.llm_reason}
                                                        </div>
                                                    )}
                                                    {(selectedDiff.llm_url || selectedDiff.llm_message_extracted_url || selectedDiff.llm_signature) && (
                                                        <div className="mt-4 pt-4 border-t border-slate-200/60 flex flex-col gap-3">
                                                            {(selectedDiff.llm_url || selectedDiff.llm_message_extracted_url) && (
                                                                <div>
                                                                    <span className="font-bold text-[10px] text-slate-400 uppercase tracking-widest block mb-1.5 flex items-center gap-1">
                                                                        🔗 Extracted URL
                                                                    </span>
                                                                    <div className="flex flex-col gap-1.5">
                                                                        {selectedDiff.llm_url && (
                                                                            <div className="bg-indigo-50/50 border border-indigo-100 p-2.5 rounded-lg">
                                                                                <a href={selectedDiff.llm_url} target="_blank" rel="noreferrer" className="text-xs text-indigo-600 break-all hover:text-indigo-800 hover:underline font-medium">
                                                                                    {selectedDiff.llm_url}
                                                                                </a>
                                                                            </div>
                                                                        )}
                                                                        {selectedDiff.llm_message_extracted_url && selectedDiff.llm_message_extracted_url !== selectedDiff.llm_url && (
                                                                            <div className="bg-slate-50 border border-slate-100 p-2 rounded-lg">
                                                                                <span className="text-[10px] text-slate-400 font-bold block mb-0.5">Original URL in Msg:</span>
                                                                                <a href={selectedDiff.llm_message_extracted_url} target="_blank" rel="noreferrer" className="text-xs text-slate-500 break-all hover:text-slate-800 hover:underline">
                                                                                    {selectedDiff.llm_message_extracted_url}
                                                                                </a>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            )}
                                                            {selectedDiff.llm_signature && (
                                                                <div>
                                                                    <span className="font-bold text-[10px] text-slate-400 uppercase tracking-widest block mb-1.5 flex items-center gap-1">
                                                                        🔑 Extracted Signature
                                                                    </span>
                                                                    <div className="bg-slate-50 border border-slate-200 p-2.5 rounded-lg">
                                                                        <div className="text-xs text-slate-700 font-mono break-all whitespace-pre-wrap">
                                                                            {selectedDiff.llm_signature}
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            )}
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

            {/* Record Diff Modal (Integrated 1:1 Viewer) */}
            {isDiffModalOpen && data && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm animate-in fade-in" onClick={() => setIsDiffModalOpen(false)}></div>
                    <div className="bg-white rounded-3xl shadow-2xl w-full max-w-7xl max-h-[90vh] overflow-hidden flex flex-col relative animate-in zoom-in-95 duration-200">
                        {/* Header */}
                        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-indigo-50/50">
                            <div>
                                <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                                    <GitCompare size={20} className="text-indigo-600" />
                                    전체 데이터 상세 비교 (Human vs LLM)
                                </h3>
                                <p className="text-xs text-slate-500 mt-1">
                                    정답(Human) 엑셀의 <strong>모든 메시지</strong>를 기준으로 AI 분석 결과를 1:1 매칭하여 보여줍니다.
                                </p>
                            </div>
                            <div className="flex items-center gap-3">
                                <button 
                                    onClick={handleSaveDiffExcel}
                                    className="px-4 py-2 bg-indigo-600 text-white text-sm font-bold rounded-xl hover:bg-indigo-700 transition-colors shadow-sm flex items-center gap-2"
                                >
                                    <Download size={16} />
                                    Excel 저장
                                </button>
                                <button onClick={() => setIsDiffModalOpen(false)} className="p-2 hover:bg-slate-200 rounded-lg transition-colors">
                                    <X size={20} className="text-slate-500" />
                                </button>
                            </div>
                        </div>
                        
                        {/* Filters & Search */}
                        <div className="px-6 py-4 border-b border-slate-100 bg-white flex items-center gap-4 overflow-x-auto">
                            <div className="flex bg-slate-100 rounded-xl p-1 gap-1">
                                {[
                                    { id: 'ALL', label: '전체 보기', icon: Database },
                                    { id: 'MATCH', label: '일치 (Match)', icon: Check },
                                    { id: 'MISMATCH', label: '불일치 (Mismatch)', icon: AlertCircle },
                                    { id: 'MISSING', label: 'AI 누락', icon: X }
                                ].map(f => (
                                    <button
                                        key={f.id}
                                        onClick={() => setDiffFilter(f.id as any)}
                                        className={cn(
                                            "px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition-all whitespace-nowrap",
                                            diffFilter === f.id
                                                ? "bg-white text-indigo-700 shadow-sm ring-1 ring-slate-200/50"
                                                : "text-slate-500 hover:text-slate-700 hover:bg-slate-200/50"
                                        )}
                                    >
                                        <f.icon size={16} className={diffFilter === f.id ? "text-indigo-600" : "opacity-50"} />
                                        {f.label}
                                        <span className={cn(
                                            "text-xs px-2 py-0.5 rounded-full",
                                            diffFilter === f.id ? "bg-indigo-50 text-indigo-600" : "bg-slate-200 text-slate-500"
                                        )}>
                                            {f.id === 'ALL' ? (data.human_based_diffs?.length || 0) :
                                             f.id === 'MATCH' ? (data.human_based_diffs?.filter(d => d.match_status === 'MATCH').length || 0) :
                                             f.id === 'MISMATCH' ? (data.human_based_diffs?.filter(d => d.match_status === 'FN' || d.match_status === 'FP').length || 0) :
                                             (data.human_based_diffs?.filter(d => d.match_status === 'MISSING_IN_LLM').length || 0)}
                                        </span>
                                    </button>
                                ))}
                            </div>
                            
                            {/* Search Box */}
                            <div className="flex-1 flex items-center justify-end px-4 gap-2 border-l border-slate-100 min-w-[250px]">
                                <Search size={16} className="text-slate-400 shrink-0" />
                                <input
                                    type="text"
                                    placeholder="메시지 내용으로 검색..."
                                    value={diffSearchText}
                                    onChange={(e) => setDiffSearchText(e.target.value)}
                                    className="w-full bg-transparent border-none text-sm focus:ring-0 text-slate-700 placeholder:text-slate-400"
                                />
                                {diffSearchText && (
                                    <div className="flex items-center gap-2">
                                        <span className="text-[10px] font-bold text-indigo-600 bg-indigo-50 px-2 py-1 rounded-md whitespace-nowrap">
                                            매칭: {(data.human_based_diffs || []).filter(item => {
                                                if (diffFilter === 'MATCH' && item.match_status !== 'MATCH') return false;
                                                if (diffFilter === 'MISMATCH' && (item.match_status !== 'FN' && item.match_status !== 'FP')) return false;
                                                if (diffFilter === 'MISSING' && item.match_status !== 'MISSING_IN_LLM') return false;
                                                return item.message_full.toLowerCase().includes(diffSearchText.toLowerCase());
                                            }).length}건
                                        </span>
                                        <button onClick={() => setDiffSearchText('')} className="p-1 hover:bg-slate-100 rounded-full transition-colors shrink-0">
                                            <X size={14} className="text-slate-400" />
                                        </button>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Integrated List Content */}
                        <div className="flex-1 overflow-auto p-0 bg-slate-50/50">
                            <div className="min-w-[1000px]">
                                {/* Table Header */}
                                <div 
                                    className="grid gap-4 px-6 py-3 bg-slate-100/50 border-b border-slate-200 text-xs font-bold text-slate-500 uppercase tracking-wider sticky top-0 z-10 backdrop-blur-md select-none"
                                    style={{ gridTemplateColumns: `${colWidths.row}px ${colWidths.message}px ${colWidths.human}px ${colWidths.llm}px ${colWidths.status}px` }}
                                >
                                    <div className="text-center relative group">
                                        Row
                                        <div onMouseDown={(e) => handleMouseDown(e, 'row')} className="absolute right-[-10px] top-1 bottom-1 w-[3px] bg-slate-200 cursor-col-resize group-hover:bg-indigo-300 hover:w-[4px] hover:bg-indigo-500 z-20 transition-all rounded" />
                                    </div>
                                    <div className="relative group">
                                        Original Message
                                        <div onMouseDown={(e) => handleMouseDown(e, 'message')} className="absolute right-[-10px] top-1 bottom-1 w-[3px] bg-slate-200 cursor-col-resize group-hover:bg-indigo-300 hover:w-[4px] hover:bg-indigo-500 z-20 transition-all rounded" />
                                    </div>
                                    <div className="relative group">
                                        Human
                                        <div onMouseDown={(e) => handleMouseDown(e, 'human')} className="absolute right-[-10px] top-1 bottom-1 w-[3px] bg-slate-200 cursor-col-resize group-hover:bg-indigo-300 hover:w-[4px] hover:bg-indigo-500 z-20 transition-all rounded" />
                                    </div>
                                    <div className="relative group">
                                        LLM (AI 분석결과)
                                        <div onMouseDown={(e) => handleMouseDown(e, 'llm')} className="absolute right-[-10px] top-1 bottom-1 w-[3px] bg-slate-200 cursor-col-resize group-hover:bg-indigo-300 hover:w-[4px] hover:bg-indigo-500 z-20 transition-all rounded" />
                                    </div>
                                    <div className="text-center">
                                        Status
                                    </div>
                                </div>
                                
                                {/* Table Body */}
                                <div>
                                    {(data.human_based_diffs || []).filter(item => {
                                        // 1. Status Filter
                                        if (diffFilter === 'MATCH' && item.match_status !== 'MATCH') return false;
                                        if (diffFilter === 'MISMATCH' && (item.match_status !== 'FN' && item.match_status !== 'FP')) return false;
                                        if (diffFilter === 'MISSING' && item.match_status !== 'MISSING_IN_LLM') return false;
                                        
                                        // 2. Text Search Filter
                                        if (diffSearchText.trim() !== '') {
                                            const query = diffSearchText.toLowerCase();
                                            return item.message_full.toLowerCase().includes(query);
                                        }
                                        return true;
                                    }).length === 0 ? (
                                        <div className="p-12 text-center text-slate-500">
                                            조건에 맞는 데이터가 없습니다.
                                        </div>
                                    ) : (
                                        <div className="divide-y divide-slate-100">
                                            {(data.human_based_diffs || []).filter(item => {
                                                if (diffFilter === 'MATCH' && item.match_status !== 'MATCH') return false;
                                                if (diffFilter === 'MISMATCH' && (item.match_status !== 'FN' && item.match_status !== 'FP')) return false;
                                                if (diffFilter === 'MISSING' && item.match_status !== 'MISSING_IN_LLM') return false;
                                                if (diffSearchText.trim() !== '') {
                                                    const query = diffSearchText.toLowerCase();
                                                    return item.message_full.toLowerCase().includes(query);
                                                }
                                                return true;
                                            }).map((item, idx) => {
                                                const isExpanded = expandedDiffs.has(idx);
                                                return (
                                                <div 
                                                    key={idx} 
                                                    onClick={() => toggleDiffExpand(idx)}
                                                    className="grid gap-4 px-6 py-4 hover:bg-slate-50/80 transition-colors group cursor-pointer"
                                                    style={{ gridTemplateColumns: `${colWidths.row}px ${colWidths.message}px ${colWidths.human}px ${colWidths.llm}px ${colWidths.status}px` }}
                                                >
                                                    
                                                    {/* 1. Row Index */}
                                                    <div className="flex items-start justify-center pt-1">
                                                        <span className="text-xs font-mono text-slate-400 bg-white border border-slate-200 rounded px-2 py-0.5 transition-colors group-hover:border-indigo-200 group-hover:text-indigo-600">
                                                            #{item.index + 1}
                                                        </span>
                                                    </div>

                                                    {/* 2. Message */}
                                                    <div className="pr-4 border-r border-slate-100 relative flex flex-col justify-between">
                                                        <p className={cn("text-sm text-slate-700 leading-relaxed font-medium break-all whitespace-pre-wrap transition-all", !isExpanded && "line-clamp-4")}>
                                                            <HighlightText text={item.message_full} highlight={diffSearchText} />
                                                        </p>
                                                        
                                                        <div className="flex justify-between items-center mt-2 group-hover:opacity-100 opacity-70 transition-opacity">
                                                            <div className="flex gap-2">
                                                                {item.match_status === 'MISSING_IN_LLM' && (
                                                                    <span className={cn(
                                                                        "text-[10px] font-bold px-1.5 py-0.5 rounded border",
                                                                        item.message_full.replace(/\s+/g, '').replace(/[\u0080-\uFFFF]/g, 'xx').length < 9 
                                                                            ? "bg-amber-50 text-amber-600 border-amber-200" 
                                                                            : "bg-slate-50 text-slate-500 border-slate-200"
                                                                    )}>
                                                                        {item.message_full.replace(/\s+/g, '').replace(/[\u0080-\uFFFF]/g, 'xx').length} bytes (공백제외)
                                                                    </span>
                                                                )}
                                                            </div>
                                                            {item.message_full.length > 150 && (
                                                                <div className="text-[10px] font-bold text-indigo-400 cursor-pointer hover:text-indigo-600 transition-colors flex items-center gap-1">
                                                                    {isExpanded ? '접기 ▲' : '더보기 ▼'}
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>

                                                    {/* 3. Human */}
                                                    <div className="pr-4 border-r border-slate-100 space-y-2">
                                                        <div className="flex items-center gap-2">
                                                            <span className={cn(
                                                                "text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wider",
                                                                item.human_is_spam ? "bg-rose-50 text-rose-600 border-rose-100" : "bg-emerald-50 text-emerald-600 border-emerald-100"
                                                            )}>
                                                                {item.human_is_spam ? 'SPAM' : 'HAM'}
                                                            </span>
                                                            {item.human_code && (
                                                                <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded border border-slate-200">
                                                                    {item.human_code}
                                                                </span>
                                                            )}
                                                        </div>
                                                        {item.human_reason && (
                                                            <div className={cn("text-xs text-slate-600 bg-white border border-slate-200 p-2 rounded-lg break-words transition-all", !isExpanded && "line-clamp-3")}>
                                                                {item.human_reason}
                                                            </div>
                                                        )}
                                                    </div>

                                                    {/* 4. LLM */}
                                                    <div className="pr-4 border-r border-slate-100 space-y-2">
                                                        {item.match_status === 'MISSING_IN_LLM' ? (
                                                            <div className="h-full flex items-center justify-center text-xs text-slate-400 italic bg-slate-50 border border-dashed border-slate-200 rounded-lg p-3">
                                                                AI 분석 내역 찾을 수 없음
                                                            </div>
                                                        ) : (
                                                            <>
                                                                <div className="flex items-center gap-2">
                                                                    <span className={cn(
                                                                        "text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wider",
                                                                        item.llm_is_spam ? "bg-rose-50 text-rose-600 border-rose-100" : "bg-emerald-50 text-emerald-600 border-emerald-100"
                                                                    )}>
                                                                        {item.llm_is_spam ? 'SPAM' : 'HAM'}
                                                                    </span>
                                                                    {item.llm_code && (
                                                                        <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded border border-slate-200">
                                                                            {item.llm_code}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                
                                                                <div className="flex flex-col gap-1 mt-1">
                                                                    {item.llm_url && (
                                                                        <div className="text-[10px] text-slate-600 flex items-start gap-1">
                                                                            <span className="font-bold whitespace-nowrap shrink-0 text-blue-600 mt-0.5" title="KISA 텍스트 파일의 URL 필드에서 입력받은 값을 분석한 결과입니다.">텍스트입력 URL:</span>
                                                                            <a href={item.llm_url.startsWith('http') ? item.llm_url : `http://${item.llm_url}`} target="_blank" rel="noopener noreferrer" className="break-all bg-blue-50 px-1 rounded border border-blue-100 hover:text-blue-600 hover:underline">{item.llm_url}</a>
                                                                        </div>
                                                                    )}
                                                                    {item.llm_message_extracted_url && (
                                                                        <div className="text-[10px] text-slate-600 flex items-start gap-1">
                                                                            <span className="font-bold whitespace-nowrap shrink-0 text-emerald-600 mt-0.5" title="메시지 본문 내용에서 AI가 직접 텍스트를 분석하여 추출/복원한 URL입니다.">메시지내 URL:</span>
                                                                            <a href={item.llm_message_extracted_url.startsWith('http') ? item.llm_message_extracted_url : `http://${item.llm_message_extracted_url}`} target="_blank" rel="noopener noreferrer" className="break-all bg-emerald-50 px-1 rounded border border-emerald-100 hover:text-emerald-600 hover:underline">{item.llm_message_extracted_url}</a>
                                                                        </div>
                                                                    )}
                                                                    {item.llm_signature && (
                                                                        <div className="text-[10px] text-slate-600 flex items-start gap-1">
                                                                            <span className="font-bold whitespace-nowrap shrink-0 text-purple-600 mt-0.5">시그니처:</span>
                                                                            <span className="break-all bg-purple-50 px-1 rounded border border-purple-100">{item.llm_signature}</span>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                                
                                                                {item.llm_reason && (
                                                                    <div className={cn("text-xs text-slate-600 bg-violet-50/50 border border-violet-100 p-2 rounded-lg break-words transition-all overflow-hidden", isExpanded ? "" : "max-h-[72px] relative")}>
                                                                        <div className="prose prose-sm prose-slate max-w-none text-[11px] leading-relaxed">
                                                                            <ReactMarkdown>{item.llm_reason}</ReactMarkdown>
                                                                        </div>
                                                                        {!isExpanded && (
                                                                            <div className="absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-violet-50/90 to-transparent pointer-events-none" />
                                                                        )}
                                                                    </div>
                                                                )}
                                                            </>
                                                        )}
                                                    </div>

                                                    {/* 5. Status Badge */}
                                                    <div className="flex flex-col items-center pt-2">
                                                        {item.match_status === 'MATCH' && (
                                                            <div className="flex flex-col items-center text-emerald-600">
                                                                <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center mb-1">
                                                                    <Check size={18} strokeWidth={3} />
                                                                </div>
                                                                <span className="text-[10px] font-bold">MATCH</span>
                                                            </div>
                                                        )}
                                                        {item.match_status === 'MISSING_IN_LLM' && (
                                                            <div className="flex flex-col items-center text-slate-400">
                                                                <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center mb-1">
                                                                    <AlertCircle size={18} />
                                                                </div>
                                                                <span className="text-[10px] font-bold whitespace-nowrap">AI MISSING</span>
                                                            </div>
                                                        )}
                                                        {(item.match_status === 'FP' || item.match_status === 'FN') && (
                                                            <div className="flex flex-col items-center text-amber-600">
                                                                <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center mb-1">
                                                                    <X size={18} strokeWidth={3} />
                                                                </div>
                                                                <span className="text-[10px] font-extrabold px-1.5 py-0.5 bg-amber-50 rounded border border-amber-200 shadow-sm mt-1">
                                                                    {item.match_status}
                                                                </span>
                                                            </div>
                                                        )}
                                                    </div>

                                                </div>
                                            );})}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Footer */}
                        <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
                            <div>Row 순번은 업로드 된 Human(정답) 엑셀의 순서 기준입니다.</div>
                        </div>
                    </div>
                </div>
            )}

        </main>
    );
}
