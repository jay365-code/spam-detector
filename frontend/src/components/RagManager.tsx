import React, { useState, useEffect } from 'react';
import { X, Edit2, Trash2, Search, Database, RefreshCw, Save, AlertCircle, Copy, Check, PenSquare } from 'lucide-react';

interface FnExample {
    id: string;
    message: string;
    label: string;
    code: string;
    category: string;
    reason: string;
    created_at?: string;
}

interface InitialData {
    message: string;
    label: 'SPAM' | 'HAM';
    code?: string;
    reason?: string;
}

interface RagManagerProps {
    isOpen: boolean;
    onClose: () => void;
    initialData?: InitialData;
}

// [Fix] Remote Server Compatibility: Use window.location.hostname for API
const API_BASE = `http://${window.location.hostname}:8000`;

// 스팸 코드 매핑


const SPAM_CATEGORY_PRESETS = [
    '도박 / 게임',
    '성인 / 유흥',
    '유흥업소',
    '통신 / 휴대폰 스팸',
    '대리운전',
    '불법 의약품',
    '금융 / 대출 사기',
    '구인 / 부업 (불법·어뷰즈)',
    '나이트클럽',
    '주식 리딩 / 사기',
    '로또 사기',
    '피싱 / 스미싱',
];

const CATEGORY_CODE_MAP: Record<string, string> = {
    '도박 / 게임': '3',
    '성인 / 유흥': '1',
    '유흥업소': '1',
    '통신 / 휴대폰 스팸': '0',
    '대리운전': '0',
    '불법 의약품': '1',
    '금융 / 대출 사기': '3',
    '구인 / 부업 (불법·어뷰즈)': '0',
    '나이트클럽': '1',
    '주식 리딩 / 사기': '2',
    '로또 사기': '2',
    '피싱 / 스미싱': '2',
};

const HAM_CATEGORY_PRESETS = [
    '정상 광고/마케팅',
    '배송/택배 알림',
    '결제/승인 알림',
    '예약/일정 안내',
    '공공/행정 안내',
    '개인 메시지',
    '기타 정상',
];

export const RagManager: React.FC<RagManagerProps> = ({ isOpen, onClose, initialData }) => {
    const [examples, setExamples] = useState<FnExample[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Form state
    // Form state
    const [editingId, setEditingId] = useState<string | null>(null);
    const [formData, setFormData] = useState({
        message: '',
        label: 'SPAM',
        code: '1',
        category: '',
        reason: ''
    });

    // Search state
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<any[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [hasSearched, setHasSearched] = useState(false);

    // List View State
    const [filterLabel, setFilterLabel] = useState<'ALL' | 'SPAM' | 'HAM'>('ALL');
    const [sortOption, setSortOption] = useState<'LATEST' | 'OLDEST' | 'MESSAGE'>('LATEST');
    const [copiedId, setCopiedId] = useState<string | null>(null);

    const [listSearchQuery, setListSearchQuery] = useState('');

    // Fetch all examples
    const fetchExamples = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch(`${API_BASE}/api/spam-rag`);
            const data = await response.json();
            if (data.success) {
                setExamples(data.data);
            } else {
                setError('데이터를 불러오는데 실패했습니다.');
            }
        } catch (err) {
            setError('서버 연결에 실패했습니다.');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            fetchExamples();
        }
    }, [isOpen]);

    // initialData가 있으면 폼에 채우기
    useEffect(() => {
        if (isOpen && initialData) {
            // 관리자 등록 시 판단 근거를 "관리자, timestamp" 형식으로 설정
            const timestamp = new Date().toISOString().slice(0, 19).replace('T', ' ');
            const adminReason = `관리자, ${timestamp}`;

            setFormData({
                message: initialData.message || '',
                label: initialData.label || 'SPAM',
                code: initialData.label === 'HAM' ? '' : (initialData.code || '1'),
                category: '',
                reason: adminReason
            });
            setEditingId(null);
        }
    }, [isOpen, initialData]);

    const handleCategoryClick = (cat: string) => {
        const newCode = CATEGORY_CODE_MAP[cat] || formData.code;
        setFormData({
            ...formData,
            category: cat,
            code: formData.label === 'SPAM' ? newCode : ''
        });
    };

    // Handle form submit (Create/Update)
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);

        try {
            const url = editingId
                ? `${API_BASE}/api/spam-rag/${editingId}`
                : `${API_BASE}/api/spam-rag`;

            const method = editingId ? 'PUT' : 'POST';

            const response = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });

            const data = await response.json();

            // HTTP 상태 코드가 성공이 아닐 경우 (4xx, 5xx 등)
            if (!response.ok) {
                if (response.status === 409) {
                    setError('이미 등록된 메시지입니다 (내용 또는 벡터 유사도 중복).');
                } else {
                    const detail = data.detail || data.message || `HTTP ${response.status}`;
                    setError(`저장에 실패했습니다: ${detail}`);
                }
                return;
            }

            if (data.success) {
                await fetchExamples();
                resetForm();
            } else {
                // 서버 응답에서 detail 또는 message 추출하여 표시
                const detail = data.detail || data.message || '알 수 없는 오류';
                setError(`저장에 실패했습니다: ${detail}`);
            }
        } catch (err: any) {
            // 네트워크 오류 또는 예외 발생 시
            const message = err?.message || '네트워크 오류';
            setError(`저장에 실패했습니다: ${message}`);
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    // Handle delete
    const handleDelete = async (id: string) => {
        if (!confirm('정말 삭제하시겠습니까?')) return;

        setLoading(true);
        try {
            const response = await fetch(`${API_BASE}/api/spam-rag/${id}`, {
                method: 'DELETE'
            });

            const data = await response.json();
            if (data.success) {
                await fetchExamples();
                // 검색 결과에서도 삭제
                setSearchResults(prev => prev.filter(item => item.id !== id));
            } else {
                setError('삭제에 실패했습니다.');
            }
        } catch (err) {
            setError('삭제 중 오류가 발생했습니다.');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    // Handle edit
    const handleEdit = (example: FnExample) => {
        setEditingId(example.id);
        setFormData({
            message: example.message,
            label: example.label as 'SPAM' | 'HAM',
            code: example.code,
            category: example.category,
            reason: example.reason
        });
    };

    // Reset form
    const resetForm = () => {
        setEditingId(null);
        setFormData({
            message: '',
            label: 'SPAM',
            code: '1',
            category: '',
            reason: ''
        });
    };

    // Handle search (Vector Search)
    const handleSearch = async () => {
        if (!searchQuery.trim()) return;

        setIsSearching(true);
        setHasSearched(true);
        try {
            // k=2: Match the Agent's Prompt Context logic (Top 2 references)
            const response = await fetch(`${API_BASE}/api/spam-rag/search?query=${encodeURIComponent(searchQuery)}&k=2`);

            if (!response.ok) {
                if (response.status === 404) {
                    setError('검색 API를 찾을 수 없습니다. 백엔드 서버를 재시작해주세요.');
                } else {
                    setError(`검색 서버 오류: ${response.status}`);
                }
                setSearchResults([]);
                return;
            }

            const data = await response.json();
            if (data.success) {
                // Backend returns { hits: [], stats: {} }
                setSearchResults(data.data.hits || []);
            }
        } catch (err) {
            console.error(err);
        } finally {
            setIsSearching(false);
        }
    };

    const handleClearSearch = () => {
        setSearchQuery('');
        setSearchResults([]);
        setHasSearched(false);
    };

    const handleCopy = async (id: string | null, text: string) => {
        try {
            await navigator.clipboard.writeText(text);
            if (id) {
                setCopiedId(id);
                setTimeout(() => setCopiedId(null), 2000);
            }
        } catch (err) {
            console.error('Failed to copy:', err);
        }
    };

    // Filter & Sort Logic for List
    const filteredAndSortedExamples = [...examples]
        .filter(ex => filterLabel === 'ALL' || ex.label === filterLabel)
        .filter(ex => listSearchQuery ? ex.message.includes(listSearchQuery) : true)
        .sort((a, b) => {
            if (sortOption === 'LATEST') return (b.created_at || '').localeCompare(a.created_at || '');
            if (sortOption === 'OLDEST') return (a.created_at || '').localeCompare(b.created_at || '');
            if (sortOption === 'MESSAGE') return a.message.localeCompare(b.message);
            return 0;
        });

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 animate-in fade-in duration-200">
            <div className="bg-slate-900 border border-slate-700 rounded-3xl w-full max-w-6xl h-[85vh] mx-4 shadow-2xl flex overflow-hidden animate-in zoom-in-95 duration-200 relative">

                {/* Global Close Button (Top Right) */}
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 p-2 hover:bg-slate-800 rounded-xl transition-colors z-50 group"
                >
                    <X size={24} className="text-slate-400 group-hover:text-white" />
                </button>

                {/* Left Panel: Form & Search */}
                <div className="w-1/2 flex flex-col border-r border-slate-800 relative bg-slate-900/50">

                    {/* Header (Fixed) */}
                    <div className="p-6 pb-2">
                        <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 bg-indigo-600 rounded-xl flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
                                    <Database size={20} />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold text-white">RAG 데이터 관리</h2>
                                    <p className="text-xs text-slate-400 font-medium">Spam/Ham 예시 데이터 등록 및 관리</p>
                                </div>
                            </div>
                            <button
                                onClick={resetForm}
                                className="px-3 py-1.5 text-xs font-bold text-indigo-400 border border-indigo-500/30 rounded-lg hover:bg-indigo-500/10 transition-colors"
                            >
                                + 신규 등록
                            </button>
                        </div>
                    </div>

                    {/* Vector Search Section (Fixed at Top) */}
                    <div className="px-6 pb-4 border-b-2 border-slate-700/50 bg-slate-900/30 z-10">
                        <div>
                            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                                <Search className="w-3 h-3 text-indigo-400" />
                                VECTOR SEARCH
                            </h3>
                            <div className="flex gap-2">
                                <div className="relative flex-1">
                                    <input
                                        type="text"
                                        value={searchQuery}
                                        onChange={(e) => setSearchQuery(e.target.value)}
                                        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                                        placeholder="등록 전 유사 메시지 검색..."
                                        className="w-full pl-9 pr-8 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-white text-sm placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                                    />
                                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                                    {searchQuery && (
                                        <button
                                            onClick={handleClearSearch}
                                            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-slate-800 rounded-full text-slate-400 hover:text-white transition-colors"
                                        >
                                            <X className="w-3 h-3" />
                                        </button>
                                    )}
                                </div>
                                <button
                                    onClick={handleSearch}
                                    disabled={isSearching}
                                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-xl text-slate-300 font-medium transition-colors border border-slate-700 text-sm whitespace-nowrap flex items-center gap-2"
                                >
                                    {isSearching ? (
                                        <>
                                            <RefreshCw className="w-4 h-4 animate-spin" />
                                            <span>검색중...</span>
                                        </>
                                    ) : (
                                        "검색"
                                    )}
                                </button>
                            </div>

                            {/* Loading State */}
                            {isSearching && (
                                <div className="mt-4 p-8 text-center text-slate-500 bg-slate-800/20 rounded-lg border border-slate-800 border-dashed animate-pulse">
                                    <div className="flex flex-col items-center gap-2">
                                        <RefreshCw className="w-5 h-5 animate-spin text-indigo-500" />
                                        <p className="text-xs">유사한 예시를 분석하고 있습니다...</p>
                                    </div>
                                </div>
                            )}

                            {hasSearched && searchResults.length === 0 && !isSearching && (
                                <div className="mt-4 p-4 text-center text-slate-500 bg-slate-800/30 rounded-lg border border-slate-700 border-dashed">
                                    <p className="text-xs">유사한 예시가 없습니다.</p>
                                </div>
                            )}

                            {searchResults.length > 0 && (
                                <div className="mt-4 space-y-2 max-h-40 overflow-y-auto custom-scrollbar">
                                    {searchResults.map((result, idx) => (
                                        <div key={idx} className="p-3 bg-slate-950 rounded-lg border border-slate-800 hover:border-slate-700 transition-colors">
                                            <div className="flex items-start justify-between gap-2">
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                                                        <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded ${result.label === 'SPAM' ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'
                                                            }`}>
                                                            {result.label}
                                                        </span>
                                                        <span className="text-[10px] text-slate-500">
                                                            유사도: {result.distance !== undefined ? ((1 - result.distance) * 100).toFixed(1) : '0.0'}%
                                                        </span>
                                                    </div>
                                                    <p className="text-xs text-slate-400 line-clamp-1">{result.message}</p>
                                                </div>
                                                <button
                                                    onClick={() => handleEdit({
                                                        id: result.id,
                                                        message: result.message,
                                                        label: result.label,
                                                        code: result.code,
                                                        category: result.category || '',
                                                        reason: result.reason || ''
                                                    })}
                                                    className="p-1 hover:bg-indigo-500/20 rounded text-slate-500 hover:text-indigo-400"
                                                    title="이 내용으로 채우기"
                                                >
                                                    <Edit2 className="w-3 h-3" />
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="p-6 flex flex-col flex-1 h-full min-h-0 overflow-y-auto custom-scrollbar bg-slate-950/20">
                        {/* Section Header */}
                        <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                            <PenSquare className="w-3 h-3 text-indigo-400" />
                            EXAMPLE REGISTRATION
                        </h3>

                        {/* Error Display */}
                        {error && (
                            <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl flex items-center gap-2 text-rose-400">
                                <AlertCircle className="w-4 h-4 shrink-0" />
                                <span className="text-xs font-medium">{error}</span>
                                <button onClick={() => setError(null)} className="ml-auto">
                                    <X className="w-3 h-3" />
                                </button>
                            </div>
                        )}

                        {/* Input Form */}
                        <form onSubmit={handleSubmit} className="space-y-4">
                            {/* Message */}
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
                                    메시지 원문 *
                                </label>
                                <textarea
                                    value={formData.message}
                                    onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                                    className="w-full h-24 px-4 py-3 bg-slate-950 border border-slate-800 rounded-2xl text-white text-sm placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all resize-y custom-scrollbar"
                                    placeholder="등록할 메시지 내용을 입력하세요..."
                                    required
                                />
                            </div>

                            {/* Status Grid */}
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">판정</label>
                                    <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800">
                                        <button
                                            type="button"
                                            onClick={() => setFormData({ ...formData, label: 'SPAM', code: '1' })}
                                            className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${formData.label === 'SPAM'
                                                ? 'bg-rose-500/20 text-rose-400 shadow-sm'
                                                : 'text-slate-500 hover:text-slate-300'
                                                }`}
                                        >
                                            SPAM
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setFormData({ ...formData, label: 'HAM', code: '' })}
                                            className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${formData.label === 'HAM'
                                                ? 'bg-emerald-500/20 text-emerald-400 shadow-sm'
                                                : 'text-slate-500 hover:text-slate-300'
                                                }`}
                                        >
                                            HAM
                                        </button>
                                    </div>
                                </div>

                                {formData.label === 'SPAM' && (
                                    <div>
                                        <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">분류 코드</label>
                                        <select
                                            value={formData.code}
                                            onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                                            className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all appearance-none"
                                        >
                                            <option value="0">0 - 기타 스팸</option>
                                            <option value="1">1 - 유해성 스팸</option>
                                            <option value="2">2 - 사기/투자 스팸</option>
                                            <option value="3">3 - 불법 도박/대출</option>
                                        </select>
                                    </div>
                                )}
                            </div>

                            {/* Category */}
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">카테고리</label>
                                <div className="flex flex-wrap gap-2 mb-3">
                                    {(formData.label === 'SPAM' ? SPAM_CATEGORY_PRESETS : HAM_CATEGORY_PRESETS).map(cat => (
                                        <button
                                            key={cat}
                                            type="button"
                                            onClick={() => handleCategoryClick(cat)}
                                            className={`px-3 py-1.5 text-xs rounded-xl border transition-all ${formData.category === cat
                                                ? 'bg-indigo-600 border-indigo-600 text-white shadow-lg shadow-indigo-500/30'
                                                : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-600 hover:text-slate-200'
                                                }`}
                                        >
                                            {cat}
                                        </button>
                                    ))}
                                </div>
                                <input
                                    type="text"
                                    value={formData.category}
                                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                                    placeholder="직접 입력..."
                                    className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all placeholder-slate-600"
                                    required
                                />
                            </div>

                            {/* Reason */}
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
                                    판단 근거 *
                                </label>
                                <textarea
                                    value={formData.reason}
                                    onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
                                    placeholder="Intent / Tactics / Action (의도 / 전술 / 행동)"
                                    className="w-full h-20 px-4 py-3 bg-slate-950 border border-slate-800 rounded-2xl text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all resize-y placeholder-slate-600 custom-scrollbar"
                                    required
                                />
                            </div>

                            {/* Submit Button */}
                            <button
                                type="submit"
                                disabled={loading}
                                className="w-full py-3.5 rounded-2xl bg-indigo-600 text-white font-bold hover:bg-indigo-500 transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-50 flex items-center justify-center gap-2"
                            >
                                {loading ? (
                                    <RefreshCw className="w-5 h-5 animate-spin" />
                                ) : (
                                    <Save className="w-5 h-5" />
                                )}
                                {editingId ? '수정 내용 저장' : '새로운 예시 등록'}
                            </button>
                        </form>
                    </div>
                </div>

                {/* Right Panel: List */}
                <div className="w-1/2 flex flex-col bg-slate-950/30">
                    {/* List Header */}
                    <div className="p-6 pb-4 border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-10 pt-12">
                        {/* Added pt-12 to avoid overlap with absolute Close button if narrow, though panel is w-1/2. 
                            Actually, Close button is global top right. 
                        */}
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-lg font-bold text-white flex items-center gap-2">
                                등록된 예시
                                <span className="px-2 py-0.5 bg-slate-800 text-slate-400 rounded-lg text-xs font-mono">
                                    {filteredAndSortedExamples.length}
                                </span>
                            </h3>
                            <div className="flex gap-2">
                                {/* List Search Input */}
                                <div className="relative">
                                    <input
                                        type="text"
                                        value={listSearchQuery}
                                        onChange={(e) => setListSearchQuery(e.target.value)}
                                        placeholder="목록 검색..."
                                        className="w-40 pl-8 pr-3 py-1.5 bg-slate-800 border-none rounded-lg text-xs text-white focus:ring-1 focus:ring-indigo-500 placeholder-slate-500 transition-all focus:w-52"
                                    />
                                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
                                </div>
                                <button
                                    onClick={fetchExamples}
                                    disabled={loading}
                                    className="p-1.5 hover:bg-slate-800 rounded-lg transition-colors text-slate-400 hover:text-white"
                                    title="새로고침"
                                >
                                    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                                </button>
                            </div>
                        </div>

                        {/* Filter & Sort */}
                        <div className="flex gap-2">
                            <select
                                value={filterLabel}
                                onChange={(e) => setFilterLabel(e.target.value as any)}
                                className="bg-slate-800 border-none text-xs text-slate-300 rounded-lg px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-medium cursor-pointer"
                            >
                                <option value="ALL">전체 보기</option>
                                <option value="SPAM">SPAM 만</option>
                                <option value="HAM">HAM 만</option>
                            </select>
                            <select
                                value={sortOption}
                                onChange={(e) => setSortOption(e.target.value as any)}
                                className="bg-slate-800 border-none text-xs text-slate-300 rounded-lg px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 ml-auto font-medium cursor-pointer"
                            >
                                <option value="LATEST">최신등록 순</option>
                                <option value="OLDEST">오래된 순</option>
                                <option value="MESSAGE">메시지 가나다순</option>
                            </select>
                        </div>
                    </div>

                    {/* List Content */}
                    <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar">
                        {loading && examples.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                                <RefreshCw className="w-8 h-8 animate-spin mb-4 text-indigo-500" />
                                <p className="text-sm font-medium">데이터를 불러오는 중입니다...</p>
                            </div>
                        ) : filteredAndSortedExamples.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-20 text-slate-600">
                                <Database className="w-12 h-12 mb-4 opacity-20" />
                                <p className="font-medium">검색 결과가 없습니다.</p>
                                <p className="text-xs mt-2 opacity-70">
                                    {listSearchQuery ? '검색어와 일치하는 항목이 없습니다.' : '등록된 데이터가 없습니다.'}
                                </p>
                            </div>
                        ) : (
                            filteredAndSortedExamples.map((example) => (
                                <div
                                    key={example.id}
                                    className={`group p-5 rounded-2xl border transition-all ${editingId === example.id
                                        ? 'bg-indigo-600/10 border-indigo-500/50 shadow-lg shadow-indigo-500/10'
                                        : 'bg-slate-900 border-slate-800 hover:border-slate-700 hover:shadow-md'
                                        }`}
                                >
                                    <div className="flex items-start justify-between gap-4">
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 mb-3 flex-wrap">
                                                <span className={`px-2 py-1 text-[10px] font-bold rounded-lg tracking-wide ${example.label === 'SPAM'
                                                    ? 'bg-rose-500/20 text-rose-400'
                                                    : 'bg-emerald-500/20 text-emerald-400'
                                                    }`}>
                                                    {example.label}
                                                </span>
                                                {example.code && (
                                                    <span className="px-2 py-1 text-[10px] font-medium bg-slate-800 text-slate-400 rounded-lg border border-slate-700">
                                                        Code: {example.code}
                                                    </span>
                                                )}
                                                {example.category && (
                                                    <span className="px-2 py-1 text-[10px] font-medium bg-indigo-500/20 text-indigo-300 rounded-lg border border-indigo-500/30">
                                                        {example.category}
                                                    </span>
                                                )}
                                            </div>
                                            <p className="text-sm text-slate-300 break-all line-clamp-3 mb-3 leading-relaxed group-hover:text-white transition-colors">
                                                {example.message}
                                            </p>
                                            <div className="flex items-center gap-4 text-[10px] text-slate-500 font-medium">
                                                <span>{new Date(example.created_at || '').toLocaleDateString()}</span>
                                            </div>
                                        </div>

                                        <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <button
                                                onClick={() => handleCopy(example.id, example.message)}
                                                className="p-1.5 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white transition-colors"
                                                title="복사"
                                            >
                                                {copiedId === example.id ? (
                                                    <Check className="w-4 h-4 text-emerald-400" />
                                                ) : (
                                                    <Copy className="w-4 h-4" />
                                                )}
                                            </button>
                                            <button
                                                onClick={() => handleEdit(example)}
                                                className="p-1.5 hover:bg-indigo-500/20 rounded-lg text-slate-400 hover:text-indigo-400 transition-colors"
                                                title="수정"
                                            >
                                                <Edit2 className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={() => handleDelete(example.id)}
                                                className="p-1.5 hover:bg-rose-500/20 rounded-lg text-slate-400 hover:text-rose-400 transition-colors"
                                                title="삭제"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
