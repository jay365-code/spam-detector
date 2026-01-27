import React, { useState, useEffect } from 'react';
import { X, Plus, Edit2, Trash2, Search, Database, RefreshCw, Save, AlertCircle } from 'lucide-react';

interface FnExample {
    id: string;
    message: string;
    label: string;
    code: string;
    category: string;
    reason: string;
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

const API_BASE = 'http://localhost:8000';

// 스팸 코드 매핑
const CODE_OPTIONS = [
    { value: '0', label: '0 - 기타 스팸 (통신, 대리운전 등)' },
    { value: '1', label: '1 - 유해성 스팸 (성인, 유흥업소 등)' },
    { value: '2', label: '2 - 사기/투자 스팸 (주식 리딩 등)' },
    { value: '3', label: '3 - 불법 도박/대출' },
];

const SPAM_CATEGORY_PRESETS = [
    '술집/유흥업소 광고',
    '성인용품/서비스 광고',
    '불법 도박 홍보',
    '주식/코인 리딩방',
    '불법 대출 광고',
    '피싱/사기 메시지',
    '기타 스팸',
];

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
    const [isEditing, setIsEditing] = useState(false);
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

    // Fetch all examples
    const fetchExamples = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch(`${API_BASE}/api/fn-examples`);
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
            setFormData({
                message: initialData.message || '',
                label: initialData.label || 'SPAM',
                code: initialData.label === 'HAM' ? '' : (initialData.code || '1'),
                category: '',
                reason: initialData.reason || ''
            });
            setEditingId(null);
        }
    }, [isOpen, initialData]);

    // Handle form submit (Create/Update)
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);

        try {
            const url = editingId 
                ? `${API_BASE}/api/fn-examples/${editingId}`
                : `${API_BASE}/api/fn-examples`;
            
            const method = editingId ? 'PUT' : 'POST';
            
            const response = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });
            
            const data = await response.json();
            
            if (data.success) {
                await fetchExamples();
                resetForm();
            } else {
                setError('저장에 실패했습니다.');
            }
        } catch (err) {
            setError('저장 중 오류가 발생했습니다.');
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
            const response = await fetch(`${API_BASE}/api/fn-examples/${id}`, {
                method: 'DELETE'
            });
            
            const data = await response.json();
            if (data.success) {
                await fetchExamples();
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
            label: example.label,
            code: example.code,
            category: example.category,
            reason: example.reason
        });
        setIsEditing(true);
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
        setIsEditing(false);
    };

    // Handle search
    const handleSearch = async () => {
        if (!searchQuery.trim()) return;
        
        setIsSearching(true);
        try {
            const response = await fetch(`${API_BASE}/api/fn-examples/search/${encodeURIComponent(searchQuery)}?k=5`);
            const data = await response.json();
            if (data.success) {
                setSearchResults(data.data);
            }
        } catch (err) {
            console.error(err);
        } finally {
            setIsSearching(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-slate-900 rounded-xl border border-slate-700 w-full max-w-6xl max-h-[90vh] flex flex-col shadow-2xl">
                
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
                    <div className="flex items-center gap-3">
                        <Database className="w-6 h-6 text-blue-400" />
                        <h2 className="text-xl font-bold text-white">스팸 RAG 관리</h2>
                        <span className="text-sm text-slate-400">FN 예시 등록/조회</span>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-slate-800 rounded-lg transition-colors"
                    >
                        <X className="w-5 h-5 text-slate-400" />
                    </button>
                </div>

                {/* Error Display */}
                {error && (
                    <div className="mx-6 mt-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center gap-2 text-red-400">
                        <AlertCircle className="w-4 h-4" />
                        <span className="text-sm">{error}</span>
                        <button onClick={() => setError(null)} className="ml-auto">
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                )}

                {/* Content */}
                <div className="flex-1 overflow-hidden flex">
                    
                    {/* Left Panel: Form */}
                    <div className="w-1/2 p-6 border-r border-slate-700 overflow-y-auto">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-lg font-semibold text-white">
                                {editingId ? '예시 수정' : '새 예시 등록'}
                            </h3>
                            {editingId && (
                                <button
                                    onClick={resetForm}
                                    className="text-sm text-slate-400 hover:text-white"
                                >
                                    + 새로 등록
                                </button>
                            )}
                        </div>

                        <form onSubmit={handleSubmit} className="space-y-4">
                            {/* Message */}
                            <div>
                                <label className="block text-sm font-medium text-slate-300 mb-1">
                                    메시지 *
                                </label>
                                <textarea
                                    value={formData.message}
                                    onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                                    placeholder="메시지 원문을 입력하세요..."
                                    className="w-full h-24 px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                                    required
                                />
                            </div>

                            {/* Label & Code */}
                            <div className="flex gap-4">
                                <div className="w-32">
                                    <label className="block text-sm font-medium text-slate-300 mb-1">
                                        판정 *
                                    </label>
                                    <select
                                        value={formData.label}
                                        onChange={(e) => {
                                            const newLabel = e.target.value;
                                            setFormData({ 
                                                ...formData, 
                                                label: newLabel,
                                                // HAM 선택 시 코드 비움, 카테고리도 초기화
                                                code: newLabel === 'HAM' ? '' : (formData.code || '1'),
                                                category: ''  // 라벨 변경 시 카테고리 초기화
                                            });
                                        }}
                                        className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    >
                                        <option value="SPAM">SPAM</option>
                                        <option value="HAM">HAM</option>
                                    </select>
                                </div>
                                <div className="flex-1">
                                    <label className="block text-sm font-medium text-slate-300 mb-1">
                                        분류 코드 {formData.label === 'SPAM' ? '*' : '(해당없음)'}
                                    </label>
                                    <select
                                        value={formData.code}
                                        onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                                        disabled={formData.label === 'HAM'}
                                        className={`w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                                            formData.label === 'HAM' ? 'opacity-50 cursor-not-allowed' : ''
                                        }`}
                                    >
                                        {formData.label === 'HAM' ? (
                                            <option value="">해당없음</option>
                                        ) : (
                                            CODE_OPTIONS.map(opt => (
                                                <option key={opt.value} value={opt.value}>
                                                    {opt.label}
                                                </option>
                                            ))
                                        )}
                                    </select>
                                </div>
                            </div>

                            {/* Category */}
                            <div>
                                <label className="block text-sm font-medium text-slate-300 mb-1">
                                    카테고리 *
                                </label>
                                <div className="flex gap-2 flex-wrap mb-2">
                                    {(formData.label === 'HAM' ? HAM_CATEGORY_PRESETS : SPAM_CATEGORY_PRESETS).map(cat => (
                                        <button
                                            key={cat}
                                            type="button"
                                            onClick={() => setFormData({ ...formData, category: cat })}
                                            className={`px-2 py-1 text-xs rounded-full border transition-colors ${
                                                formData.category === cat
                                                    ? (formData.label === 'HAM' ? 'bg-green-500 border-green-500' : 'bg-blue-500 border-blue-500') + ' text-white'
                                                    : 'border-slate-600 text-slate-400 hover:border-slate-500'
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
                                    className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    required
                                />
                            </div>

                            {/* Reason */}
                            <div>
                                <label className="block text-sm font-medium text-slate-300 mb-1">
                                    판단 근거 *
                                </label>
                                <textarea
                                    value={formData.reason}
                                    onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
                                    placeholder="왜 이 메시지가 스팸인지 근거를 작성하세요..."
                                    className="w-full h-20 px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                                    required
                                />
                            </div>

                            {/* Submit Button */}
                            <button
                                type="submit"
                                disabled={loading}
                                className="w-full py-2.5 bg-gradient-to-r from-blue-500 to-purple-500 text-white font-medium rounded-lg hover:from-blue-600 hover:to-purple-600 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                            >
                                {loading ? (
                                    <RefreshCw className="w-4 h-4 animate-spin" />
                                ) : (
                                    <Save className="w-4 h-4" />
                                )}
                                {editingId ? '수정 저장' : '등록'}
                            </button>
                        </form>

                        {/* Search Section */}
                        <div className="mt-6 pt-6 border-t border-slate-700">
                            <h3 className="text-lg font-semibold text-white mb-4">유사 예시 검색</h3>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                                    placeholder="메시지를 입력하여 유사 예시 검색..."
                                    className="flex-1 px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                                <button
                                    onClick={handleSearch}
                                    disabled={isSearching}
                                    className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors flex items-center gap-2"
                                >
                                    {isSearching ? (
                                        <RefreshCw className="w-4 h-4 animate-spin text-slate-300" />
                                    ) : (
                                        <Search className="w-4 h-4 text-slate-300" />
                                    )}
                                </button>
                            </div>

                            {searchResults.length > 0 && (
                                <div className="mt-4 space-y-2">
                                    {searchResults.map((result, idx) => (
                                        <div key={idx} className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
                                            <div className="flex items-center gap-2 mb-1">
                                                <span className={`px-1.5 py-0.5 text-xs rounded ${
                                                    result.label === 'SPAM' ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'
                                                }`}>
                                                    {result.label}
                                                </span>
                                                <span className="text-xs text-slate-500">code: {result.code}</span>
                                                <span className="text-xs text-slate-500 ml-auto">
                                                    유사도: {((1 - result.score) * 100).toFixed(1)}%
                                                </span>
                                            </div>
                                            <p className="text-sm text-slate-300 line-clamp-2">{result.message}</p>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Right Panel: List */}
                    <div className="w-1/2 p-6 overflow-y-auto">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-lg font-semibold text-white">
                                등록된 예시 ({examples.length}건)
                            </h3>
                            <button
                                onClick={fetchExamples}
                                disabled={loading}
                                className="p-2 hover:bg-slate-800 rounded-lg transition-colors"
                            >
                                <RefreshCw className={`w-4 h-4 text-slate-400 ${loading ? 'animate-spin' : ''}`} />
                            </button>
                        </div>

                        {loading && examples.length === 0 ? (
                            <div className="text-center py-8 text-slate-500">
                                <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
                                <p>불러오는 중...</p>
                            </div>
                        ) : examples.length === 0 ? (
                            <div className="text-center py-8 text-slate-500">
                                <Database className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                <p>등록된 예시가 없습니다.</p>
                                <p className="text-sm mt-1">왼쪽에서 새 예시를 등록해주세요.</p>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {examples.map((example) => (
                                    <div
                                        key={example.id}
                                        className={`p-4 rounded-lg border transition-all ${
                                            editingId === example.id
                                                ? 'bg-blue-500/10 border-blue-500/50'
                                                : 'bg-slate-800/50 border-slate-700 hover:border-slate-600'
                                        }`}
                                    >
                                        <div className="flex items-start justify-between gap-3">
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-2 flex-wrap">
                                                    <span className={`px-2 py-0.5 text-xs font-medium rounded ${
                                                        example.label === 'SPAM' 
                                                            ? 'bg-red-500/20 text-red-400' 
                                                            : 'bg-green-500/20 text-green-400'
                                                    }`}>
                                                        {example.label}
                                                    </span>
                                                    <span className="px-2 py-0.5 text-xs bg-slate-700 text-slate-300 rounded">
                                                        Code: {example.code}
                                                    </span>
                                                    <span className="px-2 py-0.5 text-xs bg-purple-500/20 text-purple-400 rounded">
                                                        {example.category}
                                                    </span>
                                                </div>
                                                <p className="text-sm text-slate-300 break-all line-clamp-2 mb-2">
                                                    {example.message}
                                                </p>
                                                <p className="text-xs text-slate-500 line-clamp-1">
                                                    근거: {example.reason}
                                                </p>
                                            </div>
                                            <div className="flex gap-1 shrink-0">
                                                <button
                                                    onClick={() => handleEdit(example)}
                                                    className="p-1.5 hover:bg-slate-700 rounded transition-colors"
                                                    title="수정"
                                                >
                                                    <Edit2 className="w-4 h-4 text-slate-400" />
                                                </button>
                                                <button
                                                    onClick={() => handleDelete(example.id)}
                                                    className="p-1.5 hover:bg-red-500/20 rounded transition-colors"
                                                    title="삭제"
                                                >
                                                    <Trash2 className="w-4 h-4 text-red-400" />
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                {/* Footer */}
                <div className="px-6 py-3 border-t border-slate-700 bg-slate-800/50">
                    <p className="text-xs text-slate-500 text-center">
                        등록된 FN 예시는 Content Agent 분석 시 자동으로 검색되어 프롬프트에 포함됩니다.
                    </p>
                </div>
            </div>
        </div>
    );
};
