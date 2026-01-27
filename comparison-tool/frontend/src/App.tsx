import React, { useState } from 'react';
import axios from 'axios';
import { Upload, FileSpreadsheet, RefreshCw, AlertCircle, ChevronRight, BarChart3, Search, Download, Database, Check, X } from 'lucide-react';
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

interface CompareResponse {
  summary: SummaryMetrics;
  diffs: DiffItem[];
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

const FileInput = ({ label, onChange, file, colorClass }: { label: string, onChange: (e: React.ChangeEvent<HTMLInputElement>) => void, file: File | null, colorClass: string }) => (
  <div className="space-y-2">
    <label className="text-sm font-semibold text-gray-700 flex items-center gap-2">
      <FileSpreadsheet size={16} /> {label}
    </label>
    <div className={cn("relative group transition-all rounded-xl border-2 border-dashed p-4 hover:bg-gray-50 flex flex-col items-center justify-center text-center cursor-pointer", file ? "border-solid bg-gray-50 border-gray-300" : "border-gray-300")}>
      <input
        type="file"
        onChange={onChange}
        accept=".xlsx"
        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
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

export default function App() {
  const [humanFile, setHumanFile] = useState<File | null>(null);
  const [llmFile, setLlmFile] = useState<File | null>(null);
  const [sheetName, setSheetName] = useState("육안분석(시뮬결과35_150)");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isConfigOpen, setIsConfigOpen] = useState(true);

  // Viewer State
  const [selectedDiff, setSelectedDiff] = useState<DiffItem | null>(null);
  const [filter, setFilter] = useState<'ALL' | 'FN' | 'FP'>('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  
  // RAG Save State
  const [ragSaveStatus, setRagSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');
  const [ragSaveMessage, setRagSaveMessage] = useState('');

  // RAG 저장 함수
  const handleSaveToRag = async (diff: DiffItem) => {
    setRagSaveStatus('saving');
    try {
      const payload = {
        message: diff.message_full,
        label: diff.human_is_spam ? 'SPAM' : 'HAM',
        code: diff.human_code || '',
        category: diff.diff_type === 'FN' ? 'FN 스팸 (AI 미탐지)' : 'FP 정상 (AI 오탐)',
        reason: diff.human_reason || `${diff.diff_type}: Human=${diff.human_is_spam ? 'SPAM' : 'HAM'}, AI=${diff.llm_is_spam ? 'SPAM' : 'HAM'}`
      };
      
      await axios.post('http://localhost:8000/api/fn-examples', payload);
      setRagSaveStatus('success');
      setRagSaveMessage('RAG에 저장되었습니다');
      setTimeout(() => setRagSaveStatus('idle'), 2000);
    } catch (err) {
      setRagSaveStatus('error');
      setRagSaveMessage('저장 실패');
      setTimeout(() => setRagSaveStatus('idle'), 2000);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>, setter: (f: File | null) => void) => {
    if (e.target.files && e.target.files[0]) {
      setter(e.target.files[0]);
    }
  };

  const handleCompare = async () => {
    if (!humanFile || !llmFile) {
      setError("Please select both files.");
      return;
    }
    setLoading(true);
    setError(null);
    setData(null);
    setSelectedDiff(null);

    const formData = new FormData();
    formData.append("human_file", humanFile);
    formData.append("llm_file", llmFile);
    formData.append("sheet_name", sheetName);

    try {
      const res = await axios.post("http://localhost:8001/compare", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
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

  return (
    <div className="min-h-screen bg-[#f8fafc] text-slate-900 font-sans pb-20">
      {/* Header */}
      <nav className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between shadow-sm sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-indigo-600 rounded-xl flex items-center justify-center text-white shadow-lg shadow-indigo-200">
            <BarChart3 size={20} className="stroke-[2.5]" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">Spam Validator</h1>
            <p className="text-xs text-slate-500 font-medium">Model Evaluation Tool</p>
          </div>
        </div>
        <div className="text-xs font-semibold text-slate-400 bg-slate-100 px-3 py-1.5 rounded-full">v1.0.0</div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">

        {/* Settings & Upload Area */}
        <div className="bg-white rounded-3xl p-8 shadow-sm border border-slate-100 transition-all duration-300">
          <div
            className="flex items-center justify-between mb-0 cursor-pointer group"
            onClick={() => setIsConfigOpen(!isConfigOpen)}
          >
            <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
              <span className="w-1 h-6 bg-indigo-500 rounded-full inline-block"></span>
              Configuration
            </h2>
            <ChevronRight
              size={20}
              className={cn("text-slate-400 transition-transform duration-300 group-hover:text-indigo-500", isConfigOpen ? "rotate-90" : "")}
            />
          </div>

          <div className={cn("grid grid-cols-1 lg:grid-cols-4 gap-8 overflow-hidden transition-all duration-500 ease-in-out", isConfigOpen ? "mt-8 max-h-[500px] opacity-100" : "max-h-0 opacity-0")}>
            {/* Sheet Name Input */}
            <div className="lg:col-span-1 space-y-2">
              <label className="text-sm font-semibold text-slate-700">Target Sheet</label>
              <input
                type="text"
                value={sheetName}
                onChange={(e) => setSheetName(e.target.value)}
                className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:bg-white outline-none transition-all"
                placeholder="e.g. Sheet1"
              />
              <p className="text-[11px] text-slate-400 pl-1">Name of the sheet to analyze</p>
            </div>

            {/* File Inputs */}
            <div className="lg:col-span-2 grid grid-cols-2 gap-4">
              <FileInput
                label="Human (Ground Truth)"
                file={humanFile}
                onChange={(e) => handleFileChange(e, setHumanFile)}
                colorClass="indigo"
              />
              <FileInput
                label="AI (Prediction)"
                file={llmFile}
                onChange={(e) => handleFileChange(e, setLlmFile)}
                colorClass="violet"
              />
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
                      <p className="text-sm text-slate-600 line-clamp-2 leading-relaxed group-hover:text-slate-900">
                        {diff.message_preview}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Detail View */}
              <div className="lg:col-span-8 bg-white border border-slate-200 rounded-2xl shadow-sm flex flex-col overflow-hidden">
                {selectedDiff ? (
                  <div className="flex-1 flex flex-col h-full">
                    <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between bg-white">
                      <div>
                        <div className="flex items-center gap-3">
                          <h3 className="text-xl font-bold text-slate-900">Analysis Detail</h3>
                          <span className={cn(
                            "px-2.5 py-1 rounded-full text-xs font-bold border",
                            selectedDiff.diff_type === 'FN'
                              ? "bg-rose-50 text-rose-700 border-rose-100"
                              : "bg-amber-50 text-amber-700 border-amber-100"
                          )}>
                            {selectedDiff.diff_type === 'FN' ? 'Missed Spam (FN)' : 'False Alarm (FP)'}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400 mt-2 font-mono flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full bg-slate-300"></span>
                          Key: {selectedDiff.match_key}
                        </p>
                      </div>
                    </div>

                    <div className="p-8 flex-1 overflow-y-auto space-y-8">
                      {/* Message Content */}
                      <div>
                        <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Message Content</label>
                        <div className="bg-white p-6 rounded-2xl border border-slate-200 text-slate-700 text-sm leading-7 whitespace-pre-wrap font-sans shadow-sm">
                          {selectedDiff.message_full}
                        </div>
                      </div>

                      {/* Comparison Grid */}
                      <div className="grid grid-cols-2 gap-6">
                        {/* Human */}
                        <div className="bg-slate-50 rounded-2xl p-5 border border-slate-100 flex flex-col h-full">
                          <div className="flex items-center justify-between mb-4">
                            <span className="text-sm font-bold text-slate-700 flex items-center gap-2">
                              <span className="w-2 h-2 rounded-full bg-indigo-500"></span> Human Label
                              {/* RAG 저장 버튼 */}
                              <button
                                onClick={() => handleSaveToRag(selectedDiff)}
                                disabled={ragSaveStatus === 'saving'}
                                className={cn(
                                  "ml-1 p-1 rounded-md transition-all",
                                  ragSaveStatus === 'saving' && "animate-pulse",
                                  ragSaveStatus === 'success' && "bg-emerald-100 text-emerald-600",
                                  ragSaveStatus === 'error' && "bg-rose-100 text-rose-600",
                                  ragSaveStatus === 'idle' && "hover:bg-indigo-100 text-slate-400 hover:text-indigo-600"
                                )}
                                title="RAG DB에 저장"
                              >
                                {ragSaveStatus === 'saving' && <RefreshCw size={14} className="animate-spin" />}
                                {ragSaveStatus === 'success' && <Check size={14} />}
                                {ragSaveStatus === 'error' && <X size={14} />}
                                {ragSaveStatus === 'idle' && <Database size={14} />}
                              </button>
                              {ragSaveStatus !== 'idle' && (
                                <span className={cn(
                                  "text-[10px] font-medium",
                                  ragSaveStatus === 'success' && "text-emerald-600",
                                  ragSaveStatus === 'error' && "text-rose-600",
                                  ragSaveStatus === 'saving' && "text-slate-500"
                                )}>
                                  {ragSaveStatus === 'saving' ? '저장 중...' : ragSaveMessage}
                                </span>
                              )}
                            </span>
                            {selectedDiff.human_is_spam ? (
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-extrabold text-white bg-rose-500 px-2 py-0.5 rounded">SPAM</span>
                                {selectedDiff.human_code && (
                                  <span className="text-[10px] font-mono font-bold text-slate-500 bg-white border border-slate-200 px-1.5 py-0.5 rounded shadow-sm">
                                    {selectedDiff.human_code}
                                  </span>
                                )}
                              </div>
                            ) : (
                              <span className="text-xs font-extrabold text-white bg-emerald-500 px-2 py-0.5 rounded">HAM</span>
                            )}
                          </div>
                          {selectedDiff.human_reason && (
                            <div className="mt-auto pt-2 border-t border-slate-100">
                              <p className="text-[10px] uppercase font-bold text-slate-400 mb-1">Reason</p>
                              <p className="text-sm text-slate-700 font-medium">{selectedDiff.human_reason}</p>
                            </div>
                          )}
                          {selectedDiff.diff_type === 'FN' && selectedDiff.policy_interpretation && (
                            <div className="mt-2 pt-2 border-t border-slate-200">
                              <p className="text-[10px] uppercase font-bold text-slate-400 mb-1">정책 맥락</p>
                              <span className="inline-block px-2 py-1 bg-amber-100 text-amber-800 text-xs rounded-md font-semibold">
                                {selectedDiff.policy_interpretation}
                              </span>
                            </div>
                          )}
                        </div>

                        {/* LLM */}
                        <div className="bg-slate-50 rounded-2xl p-5 border border-slate-100 relative overflow-hidden flex flex-col h-full">
                          <div className="absolute top-0 left-0 w-1 h-full bg-violet-500"></div>
                          <div className="flex items-center justify-between mb-4 pl-2">
                            <span className="text-sm font-bold text-slate-700 flex items-center gap-2">
                              <span className="w-2 h-2 rounded-full bg-violet-500"></span> AI Prediction
                            </span>
                            {selectedDiff.llm_is_spam ? (
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-extrabold text-white bg-rose-500 px-2 py-0.5 rounded">SPAM</span>
                                {selectedDiff.llm_code && (
                                  <span className="text-[10px] font-mono font-bold text-slate-500 bg-white border border-slate-200 px-1.5 py-0.5 rounded shadow-sm">
                                    {selectedDiff.llm_code}
                                  </span>
                                )}
                              </div>
                            ) : (
                              <span className="text-xs font-extrabold text-white bg-emerald-500 px-2 py-0.5 rounded">HAM</span>
                            )}
                          </div>
                          {selectedDiff.llm_reason && (
                            <div className="mt-auto pt-2 border-t border-slate-100 ml-2">
                              <p className="text-[10px] uppercase font-bold text-slate-400 mb-1">Reason</p>
                              <p className="text-sm text-slate-700 font-medium">{selectedDiff.llm_reason}</p>
                            </div>
                          )}
                          {selectedDiff.diff_type === 'FP' && selectedDiff.policy_interpretation && (
                            <div className="mt-2 pt-2 border-t border-slate-200 ml-2">
                              <p className="text-[10px] uppercase font-bold text-slate-400 mb-1">정책 맥락</p>
                              <span className="inline-block px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded-md font-semibold">
                                {selectedDiff.policy_interpretation}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-slate-300 p-12 text-center bg-slate-50/50">
                    <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center shadow-sm mb-4">
                      <Search size={32} className="text-slate-200" />
                    </div>
                    <p className="text-lg font-semibold text-slate-600">No Selection</p>
                    <p className="text-sm mt-1 max-w-xs">Select a mismatched item from the list to analyze the difference.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
