import { useState } from 'react';
import axios from 'axios';
import {
    XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    ComposedChart, Area, Line
} from 'recharts';
import {
    FolderSearch, RefreshCw, ChevronRight, AlertCircle, BarChart3,
    ArrowLeft, Search, CheckCircle2
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { FolderPickerModal } from '../FolderPickerModal';
import { useEffect } from 'react'; // Added useEffect import

// --- Utility ---
function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

// --- Types ---
interface DailySummary {
    date: string;
    sources: string[];
    tp: number;
    tn: number;
    fp: number;
    fn: number;
    accuracy: number;
    kappa: number;
    fn_rate: number;
    mcc: number;
    primary_status: string;
    primary_color: 'success' | 'warning' | 'danger';
}

interface TrendResponse {
    dates: string[];
    kappas: number[];
    fn_rates: number[];
    daily_summaries: DailySummary[];
}

interface DiffDetail {
    diff_id: string;
    diff_type: "FN" | "FP";
    message_preview: string;
    message_full: string;
    human_label_raw: string;
    llm_label_raw: string;
    human_code: string;
    llm_code: string;
    human_is_spam: boolean;
    llm_is_spam: boolean;
    human_reason: string;
    llm_reason: string;
    match_key: string;
    policy_interpretation: string;
    source: string;
}

interface SourceBreakdown {
    source: string;
    tp: number;
    tn: number;
    fp: number;
    fn: number;
    kappa: number;
    accuracy: number;
}

interface DailyDetailResponse {
    date: string;
    summary: any;
    source_breakdown: SourceBreakdown[];
    diffs: DiffDetail[];
}

export default function MonitorPage() {
    // --- State --- 
    // Trend State
    const [folderPath, setFolderPath] = useState(localStorage.getItem('monitor_folder_path') || '');
    const [yAxisMin, setYAxisMin] = useState(0.6);
    const [visibleMetrics, setVisibleMetrics] = useState<{ [key: string]: boolean }>({
        accuracy: true,
        kappa: true,
        mcc: true,
        precision: true,
        recall: true
    });
    const [loading, setLoading] = useState(false);
    const [trendData, setTrendData] = useState<TrendResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isFolderPickerOpen, setIsFolderPickerOpen] = useState(false);

    // Detail View State
    // Detail View State
    const [selectedDate, setSelectedDate] = useState<string | null>(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailData, setDetailData] = useState<DailyDetailResponse | null>(null);
    const [detailFilter, setDetailFilter] = useState<'ALL' | 'FN' | 'FP'>('ALL');
    const [detailSource, setDetailSource] = useState<string | null>(null);
    const [detailSearch, setDetailSearch] = useState('');

    // --- Actions ---

    // Save path persistence
    useEffect(() => {
        if (folderPath) {
            localStorage.setItem('monitor_folder_path', folderPath);
        }
    }, [folderPath]);

    const handleSelectFolder = () => {
        setIsFolderPickerOpen(true);
    };

    const handleFolderPicked = (path: string) => {
        setFolderPath(path);
        // Optional: Auto load?
        // handleLoadTrend(); // Let user click load manually to be safe
    };

    const handleLoadTrend = async () => {
        setLoading(true);
        setError(null);
        setSelectedDate(null);

        try {
            const res = await axios.get(`http://localhost:8001/api/monitor/trend`, {
                params: { folder_path: folderPath }
            });
            setTrendData(res.data);
        } catch (err: any) {
            console.error(err);
            setError(err.response?.data?.detail || "Failed to load trend data.");
        } finally {
            setLoading(false);
        }
    };

    const handleViewDetail = async (date: string) => {
        setSelectedDate(date);
        setDetailLoading(true);
        setDetailData(null);
        setDetailFilter('ALL');
        setDetailSearch('');

        try {
            const res = await axios.get(`http://localhost:8001/api/monitor/day/${date}`, {
                params: { folder_path: folderPath }
            });
            setDetailData(res.data);
        } catch (err: any) {
            console.error(err);
            setError(err.response?.data?.detail || `Failed to load detail for ${date}`);
            setSelectedDate(null);
        } finally {
            setDetailLoading(false);
        }
    };

    const handleBackToTrend = () => {
        setSelectedDate(null);
        setDetailData(null);
    };

    const handleLegendClick = (o: any) => {
        const { dataKey } = o;
        setVisibleMetrics(prev => ({
            ...prev,
            [dataKey]: !prev[dataKey]
        }));
    };

    // --- Helpers ---
    const formatDate = (dateStr: string) => {
        if (dateStr && dateStr.length === 8) {
            return `${dateStr.substring(0, 4)}.${dateStr.substring(4, 6)}.${dateStr.substring(6, 8)}`;
        }
        return dateStr;
    };

    // --- Renderers ---

    const renderTrendView = () => (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Charts Section */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Combined Chart (Kappa + MCC + Accuracy) */}
                <div className="lg:col-span-2 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
                    <h3 className="text-sm font-bold text-slate-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                        <BarChart3 size={16} /> Performance Trends
                    </h3>
                    <div className="h-[350px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <ComposedChart
                                data={trendData?.daily_summaries?.map(day => {
                                    const tp = day.tp || 0;
                                    const fp = day.fp || 0;
                                    const fn = day.fn || 0;
                                    const precision = tp + fp > 0 ? tp / (tp + fp) : 0;
                                    const recall = tp + fn > 0 ? tp / (tp + fn) : 0;
                                    return {
                                        ...day,
                                        precision,
                                        recall
                                    };
                                })}
                                margin={{ top: 20, right: 0, left: 0, bottom: 0 }}
                            >
                                <defs>
                                    <linearGradient id="colorAccuracy" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.2} />
                                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="4 4" vertical={false} stroke="#f1f5f9" />
                                <XAxis
                                    dataKey="date"
                                    tick={{ fontSize: 11, fill: '#64748b' }}
                                    axisLine={false}
                                    tickLine={false}
                                    tickFormatter={(value) => formatDate(value).substring(5)} // Show MM.DD only for X-Axis to save space? Or full? Let's use MM.DD as it was before but formatted
                                    dy={10}
                                />
                                {/* Accuracy Axis */}
                                <YAxis
                                    yAxisId="left"
                                    domain={[yAxisMin, 1]}
                                    tick={{ fontSize: 11, fill: '#64748b' }}
                                    axisLine={false}
                                    tickLine={false}
                                    tickFormatter={(value) => `${Math.round(value * 100)}%`}
                                    label={{ value: "Accuracy", angle: -90, position: 'insideLeft', fontSize: 11, fill: '#6366f1', fontWeight: 600 }}
                                />
                                {/* Coefficient Axis */}
                                <YAxis
                                    yAxisId="right"
                                    orientation="right"
                                    domain={[yAxisMin, 1]}
                                    tick={{ fontSize: 11, fill: '#64748b' }}
                                    axisLine={false}
                                    tickLine={false}
                                    tickFormatter={(value) => value.toFixed(1)}
                                    label={{ value: "Kappa / MCC", angle: 90, position: 'insideRight', fontSize: 11, fill: '#64748b', fontWeight: 600 }}
                                />
                                <Tooltip
                                    contentStyle={{
                                        borderRadius: '16px',
                                        border: '1px solid #f1f5f9',
                                        boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
                                        padding: '12px 16px'
                                    }}
                                    labelFormatter={(label) => formatDate(label)}
                                    formatter={(value: any, name: any) => {
                                        if (value === undefined || value === null) return [value, name];
                                        const num = Number(value);
                                        if (isNaN(num)) return [value, name];
                                        if (name === 'Accuracy') return [`${(num * 100).toFixed(1)}%`, name];
                                        return [num.toFixed(4), name];
                                    }}
                                />
                                <Legend
                                    onClick={handleLegendClick}
                                    cursor="pointer"
                                    wrapperStyle={{ paddingTop: '20px' }}
                                    iconType="circle"
                                />
                                <Area
                                    type="monotone"
                                    yAxisId="left"
                                    dataKey="accuracy"
                                    name="Accuracy"
                                    fill="url(#colorAccuracy)"
                                    stroke="#6366f1"
                                    strokeWidth={3}
                                    dot={{ r: 4, fill: '#fff', stroke: '#6366f1', strokeWidth: 2 }}
                                    activeDot={{ r: 6, strokeWidth: 2, fill: '#fff', stroke: '#6366f1' }}
                                    hide={!visibleMetrics.accuracy}
                                />
                                <Line
                                    type="monotone"
                                    yAxisId="right"
                                    dataKey="kappa"
                                    name="Kappa"
                                    stroke="#d946ef"
                                    strokeWidth={3}
                                    dot={{ r: 4, fill: '#fff', stroke: '#d946ef', strokeWidth: 2 }}
                                    activeDot={{ r: 6, strokeWidth: 0, fill: '#d946ef' }}
                                    hide={!visibleMetrics.kappa}
                                />
                                {/* MCC is not in TrendResponse interface yet, need to add it or calculate it? 
                                    Wait, DailySummary interface has kappa, accuracy, fn_rate. 
                                    It DOES NOT have MCC.
                                    I need to check if backend sends MCC in 'daily_summaries'.
                                    Checking backend logic... 
                                    I should probably update the interface and assume backend sends it or I might need to update backend?
                                    Let's check backend response structure or `metrics.py` again.
                                    The user asked "KAPPA, MCC는 하나의 그래포에 표시하고 Accuracy 추가해".
                                    I need to ensure MCC is available.
                                    If not, I might need to update backend too.
                                    For now, I'll add it to the Interface and Chart, assuming I'll fix backend if needed.
                                 */}
                                <Line
                                    type="monotone"
                                    yAxisId="right"
                                    dataKey="mcc"
                                    name="MCC"
                                    stroke="#14b8a6"
                                    strokeWidth={3}
                                    dot={{ r: 4, fill: '#fff', stroke: '#14b8a6', strokeWidth: 2 }}
                                    activeDot={{ r: 6, strokeWidth: 0, fill: '#14b8a6' }}
                                    hide={!visibleMetrics.mcc}
                                />
                                <Line
                                    type="monotone"
                                    yAxisId="right"
                                    dataKey="precision"
                                    name="Precision"
                                    stroke="#f59e0b"
                                    strokeWidth={3}
                                    dot={{ r: 4, fill: '#fff', stroke: '#f59e0b', strokeWidth: 2 }}
                                    activeDot={{ r: 6, strokeWidth: 0, fill: '#f59e0b' }}
                                    hide={!visibleMetrics.precision}
                                />
                                <Line
                                    type="monotone"
                                    yAxisId="right"
                                    dataKey="recall"
                                    name="Recall"
                                    stroke="#3b82f6"
                                    strokeWidth={3}
                                    dot={{ r: 4, fill: '#fff', stroke: '#3b82f6', strokeWidth: 2 }}
                                    activeDot={{ r: 6, strokeWidth: 0, fill: '#3b82f6' }}
                                    hide={!visibleMetrics.recall}
                                />
                            </ComposedChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>

            {/* Daily Summary Table */}
            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                    <h3 className="font-bold text-slate-700">Daily Analysis Summary</h3>
                    <span className="text-xs font-medium text-slate-400">Click row for details</span>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                        <thead className="text-xs text-slate-500 uppercase bg-slate-50 border-b border-slate-100">
                            <tr>
                                <th className="px-6 py-3 font-semibold">Date</th>
                                <th className="px-6 py-3 font-semibold text-center">Sources</th>
                                <th className="px-6 py-3 font-semibold text-center">Matched</th>
                                <th className="px-6 py-3 font-semibold text-center">Accuracy</th>
                                <th className="px-6 py-3 font-semibold text-center">Kappa</th>
                                <th className="px-6 py-3 font-semibold text-center">FN Rate</th>
                                <th className="px-6 py-3 font-semibold text-center">Status</th>
                                <th className="px-6 py-3 text-right">Action</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {trendData?.daily_summaries.map((day) => (
                                <tr
                                    key={day.date}
                                    onClick={() => handleViewDetail(day.date)}
                                    className="bg-white hover:bg-indigo-50/50 cursor-pointer transition-colors group"
                                >
                                    <td className="px-6 py-4 font-bold text-slate-800">{formatDate(day.date)}</td>
                                    <td className="px-6 py-4 text-center">
                                        <div className="flex justify-center gap-1">
                                            {day.sources.map(s => (
                                                <span key={s} className="px-1.5 py-0.5 bg-slate-100 rounded text-[10px] font-mono text-slate-500">{s}</span>
                                            ))}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-center text-slate-600">
                                        {(day.tp + day.tn + day.fp + day.fn).toLocaleString()}
                                    </td>
                                    <td className="px-6 py-4 text-center font-medium text-slate-700">
                                        {(day.accuracy * 100).toFixed(1)}%
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <span className={cn(
                                            "px-2 py-1 rounded-full text-xs font-bold",
                                            day.kappa >= 0.6 ? "bg-emerald-50 text-emerald-700" :
                                                day.kappa >= 0.4 ? "bg-amber-50 text-amber-700" :
                                                    "bg-rose-50 text-rose-700"
                                        )}>
                                            {day.kappa.toFixed(3)}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-center font-medium text-rose-600">
                                        {(day.fn_rate * 100).toFixed(1)}%
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <span className={cn(
                                            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold border",
                                            day.primary_color === 'success' ? "bg-emerald-50 text-emerald-700 border-emerald-100" :
                                                day.primary_color === 'warning' ? "bg-amber-50 text-amber-700 border-amber-100" :
                                                    "bg-rose-50 text-rose-700 border-rose-100"
                                        )}>
                                            {day.primary_status}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <ChevronRight size={16} className="text-slate-300 group-hover:text-indigo-400 ml-auto transition-colors" />
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>


        </div>
    );

    const renderDetailView = () => {
        if (detailLoading || !detailData) return <div className="p-12 text-center text-slate-400 flex items-center justify-center gap-2"><RefreshCw className="animate-spin" size={20} /> Loading detail...</div>;

        const filteredDiffs = detailData.diffs.filter(d => {
            if (detailFilter !== 'ALL' && d.diff_type !== detailFilter) return false;
            if (detailSource && d.source !== detailSource) return false; // Filter by source if selected
            if (detailSearch && !d.message_full.toLowerCase().includes(detailSearch.toLowerCase())) return false;
            return true;
        });

        return (
            <div className="space-y-6 animate-in fade-in zoom-in-95 duration-300">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <button
                        onClick={handleBackToTrend}
                        className="flex items-center gap-2 text-slate-500 hover:text-slate-800 font-bold transition-colors"
                    >
                        <ArrowLeft size={20} />
                        Back to Trend
                    </button>
                    <h2 className="text-2xl font-bold text-slate-900 flex items-center gap-3">
                        <span className="w-1.5 h-8 bg-indigo-500 rounded-full"></span>
                        {detailData.date} Analysis
                    </h2>
                </div>

                {/* Source Breakdown Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {detailData.source_breakdown.map(src => {
                        const isSelected = detailSource === src.source;
                        return (
                            <div
                                key={src.source}
                                onClick={() => {
                                    if (isSelected && detailFilter === 'ALL') {
                                        setDetailSource(null); // Toggle off if already selected and ALL
                                    } else {
                                        setDetailSource(src.source);
                                        setDetailFilter('ALL');
                                    }
                                }}
                                className={cn(
                                    "bg-white p-5 rounded-xl border shadow-sm flex flex-col gap-3 cursor-pointer transition-all duration-200 relative overflow-hidden group hover:shadow-md",
                                    isSelected ? "border-indigo-500 ring-1 ring-indigo-500 shadow-indigo-100" : "border-slate-200 hover:border-indigo-200"
                                )}
                            >
                                {isSelected && (
                                    <div className="absolute top-0 right-0 p-1.5 bg-indigo-500 rounded-bl-xl shadow-sm">
                                        <CheckCircle2 size={12} className="text-white" />
                                    </div>
                                )}
                                <div className="flex items-center justify-between">
                                    <span className={cn("px-2 py-1 rounded text-xs font-bold transition-colors", isSelected ? "bg-indigo-100 text-indigo-700" : "bg-slate-100 text-slate-600")}>Source {src.source}</span>
                                    <span className={cn(
                                        "text-xs font-bold px-2 py-0.5 rounded-full",
                                        src.kappa >= 0.6 ? "text-emerald-600 bg-emerald-50" : "text-amber-600 bg-amber-50"
                                    )}>
                                        κ={src.kappa.toFixed(3)}
                                    </span>
                                </div>
                                <div className="grid grid-cols-2 gap-4 text-center mt-2">
                                    <div>
                                        <p className="text-[10px] font-bold text-slate-400 uppercase">Total</p>
                                        <p className="text-lg font-bold text-slate-800">{(src.tp + src.tn + src.fp + src.fn).toLocaleString()}</p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] font-bold text-slate-400 uppercase">Accuracy</p>
                                        <p className="text-lg font-bold text-indigo-600">{(src.accuracy * 100).toFixed(1)}%</p>
                                    </div>
                                </div>
                                <div className="flex gap-2 mt-auto">
                                    <div
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setDetailSource(src.source);
                                            setDetailFilter('FN');
                                        }}
                                        className={cn(
                                            "flex-1 rounded-lg p-2 text-center transition-colors hover:bg-rose-100",
                                            (isSelected && detailFilter === 'FN') ? "bg-rose-100 ring-1 ring-rose-400" : "bg-rose-50"
                                        )}
                                    >
                                        <p className="text-[10px] text-rose-400 font-bold">FN</p>
                                        <p className="text-sm font-bold text-rose-700">{src.fn}</p>
                                    </div>
                                    <div
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setDetailSource(src.source);
                                            setDetailFilter('FP');
                                        }}
                                        className={cn(
                                            "flex-1 rounded-lg p-2 text-center transition-colors hover:bg-amber-100",
                                            (isSelected && detailFilter === 'FP') ? "bg-amber-100 ring-1 ring-amber-400" : "bg-amber-50"
                                        )}
                                    >
                                        <p className="text-[10px] text-amber-400 font-bold">FP</p>
                                        <p className="text-sm font-bold text-amber-700">{src.fp}</p>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>

                {/* Diffs List */}
                <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden min-h-[500px] flex flex-col">
                    <div className="p-4 border-b border-slate-100 bg-slate-50 space-y-3">
                        <div className="flex items-center justify-between">
                            <h3 className="font-bold text-slate-700 flex items-center gap-2">
                                Mismatch Analysis
                                {detailSource && (
                                    <span className="px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 text-xs font-bold border border-indigo-200">
                                        Source {detailSource}
                                    </span>
                                )}
                            </h3>
                            <div className="flex gap-2">
                                <button onClick={() => setDetailFilter('ALL')} className={cn("px-3 py-1.5 rounded-lg text-xs font-bold transition-all", detailFilter === 'ALL' ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-slate-200")}>ALL</button>
                                <button onClick={() => setDetailFilter('FN')} className={cn("px-3 py-1.5 rounded-lg text-xs font-bold transition-all", detailFilter === 'FN' ? "bg-rose-600 text-white" : "text-slate-500 hover:bg-slate-200")}>FN</button>
                                <button onClick={() => setDetailFilter('FP')} className={cn("px-3 py-1.5 rounded-lg text-xs font-bold transition-all", detailFilter === 'FP' ? "bg-amber-600 text-white" : "text-slate-500 hover:bg-slate-200")}>FP</button>
                            </div>
                        </div>
                        <div className="relative">
                            <Search className="absolute left-3 top-2.5 text-slate-400" size={16} />
                            <input
                                type="text"
                                placeholder="Search message content..."
                                value={detailSearch}
                                onChange={(e) => setDetailSearch(e.target.value)}
                                className="w-full pl-9 pr-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-100 outline-none text-sm"
                            />
                        </div>
                    </div>

                    <div className="overflow-y-auto flex-1 p-0">
                        <table className="w-full text-sm text-left">
                            <thead className="text-xs text-slate-500 uppercase bg-slate-50 border-b border-slate-100 sticky top-0">
                                <tr>
                                    <th className="px-5 py-3 w-20 text-center">Type</th>
                                    <th className="px-5 py-3 w-20 text-center">Source</th>
                                    <th className="px-5 py-3 w-1/4">Message Preview</th>
                                    <th className="px-5 py-3">Reason (AI)</th>
                                    <th className="px-5 py-3 w-28 text-center">Analysis</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {filteredDiffs.map((diff: DiffDetail, idx: number) => (
                                    <tr key={`${diff.diff_id}-${idx}`} className="hover:bg-slate-50 transition-colors">
                                        <td className="px-5 py-4 text-center">
                                            <span className={cn(
                                                "px-2 py-1 rounded text-[10px] font-bold border",
                                                diff.diff_type === 'FN' ? "bg-rose-50 text-rose-700 border-rose-100" : "bg-amber-50 text-amber-700 border-amber-100"
                                            )}>
                                                {diff.diff_type}
                                            </span>
                                        </td>
                                        <td className="px-5 py-4 text-center">
                                            <span className="px-1.5 py-0.5 bg-slate-100 rounded text-xs font-mono text-slate-500">{diff.source}</span>
                                        </td>
                                        <td className="px-5 py-4 relative group">
                                            {/* Default clamped preview */}
                                            <p className="text-slate-800 font-medium line-clamp-2 text-xs">
                                                {diff.message_preview}
                                            </p>

                                            {/* Full Text Tooltip on Hover */}
                                            <div className="hidden group-hover:block absolute top-0 left-0 z-50 w-[450px] p-4 bg-white border border-slate-200 rounded-xl shadow-2xl transition-all">
                                                <div className="flex items-center justify-between mb-2">
                                                    <span className="text-[10px] uppercase font-bold text-slate-400">Full Message</span>
                                                    <span className="text-[10px] text-slate-400 font-mono">{diff.message_full?.length || 0} chars</span>
                                                </div>
                                                <p className="text-slate-800 text-xs whitespace-pre-wrap leading-relaxed max-h-[300px] overflow-y-auto">
                                                    {diff.message_full || diff.message_preview}
                                                </p>
                                            </div>

                                            <div className="flex gap-2 mt-1.5 relative z-0">
                                                {diff.llm_code && diff.llm_code !== '0' && <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-50 text-violet-700 border border-violet-100">AI Code: {diff.llm_code}</span>}
                                                {diff.diff_type === 'FN' && diff.human_code && (
                                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-100">
                                                        Human Code: {diff.human_code}
                                                    </span>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-5 py-4 text-xs text-slate-600 leading-relaxed group hover:whitespace-normal hover:overflow-visible hover:relative hover:z-10 hover:bg-white hover:shadow-lg hover:rounded-lg hover:p-3">
                                            {diff.llm_reason}
                                        </td>
                                        <td className="px-5 py-4 text-center">
                                            <span className="text-[10px] text-slate-400 font-mono">{idx + 1}</span>
                                        </td>
                                    </tr>
                                ))}
                                {filteredDiffs.length === 0 && (
                                    <tr>
                                        <td colSpan={5} className="py-20 text-center text-slate-400">
                                            No items match your filter
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        );
    };

    return (
        <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
            {/* Configuration Area */}
            <div className="bg-white rounded-3xl p-8 shadow-sm border border-slate-100 transition-all duration-300">
                <div className="flex items-end gap-4">
                    <div className="flex-1 space-y-2">
                        <label
                            className="text-sm font-semibold text-slate-700 flex items-center gap-2 group cursor-pointer hover:text-indigo-600 transition-colors"
                            onClick={handleSelectFolder}
                            title="폴더 선택 (브라우저 지원 시)"
                        >
                            <FolderSearch size={16} className="text-indigo-500 group-hover:scale-110 transition-transform" /> Target Folder
                        </label>
                        <input
                            type="text"
                            value={folderPath}
                            onChange={(e) => setFolderPath(e.target.value)}
                            className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:bg-white outline-none transition-all font-mono text-slate-600"
                            placeholder="C:\path\to\json\files"
                        />
                    </div>
                    <div className="w-[150px] space-y-2">
                        <label className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                            <BarChart3 size={16} className="text-slate-400" /> Y-Axis Min
                        </label>
                        <input
                            type="number"
                            min="0"
                            max="1"
                            step="0.1"
                            value={yAxisMin}
                            onChange={(e) => setYAxisMin(parseFloat(e.target.value))}
                            className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:bg-white outline-none transition-all font-mono text-slate-600 text-center"
                        />
                    </div>
                    <button
                        onClick={handleLoadTrend}
                        disabled={loading}
                        className="h-[46px] px-8 bg-slate-900 hover:bg-slate-800 text-white rounded-xl font-bold text-sm transition-all shadow-lg shadow-slate-200 disabled:opacity-70 disabled:shadow-none flex items-center gap-2"
                    >
                        {loading ? <RefreshCw className="animate-spin" size={18} /> : <CheckCircle2 size={18} />}
                        Load Trend
                    </button>
                </div>
                {error && (
                    <div className="mt-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm flex items-center gap-2">
                        <AlertCircle size={16} /> {error}
                    </div>
                )}
            </div>

            {trendData && !selectedDate && renderTrendView()}
            {selectedDate && renderDetailView()}

            {/* Folder Picker Modal */}
            <FolderPickerModal
                isOpen={isFolderPickerOpen}
                onClose={() => setIsFolderPickerOpen(false)}
                onSelect={handleFolderPicked}
                initialPath={folderPath}
            />
        </main>
    );
}
