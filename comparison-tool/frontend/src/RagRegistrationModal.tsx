import React, { useState, useEffect } from 'react';
import { X, Database, Save, AlertCircle, RefreshCw } from 'lucide-react';

interface RagRegistrationModalProps {
    isOpen: boolean;
    onClose: () => void;
    data: {
        message: string;
        label: string;
        code: string;
        diffType: 'FN' | 'FP';
        reason: string;
    } | null;
    onSave: (payload: any) => Promise<void>;
}

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

export const RagRegistrationModal: React.FC<RagRegistrationModalProps> = ({ isOpen, onClose, data, onSave }) => {
    const [formData, setFormData] = useState({
        message: '',
        label: 'SPAM',
        code: '',
        category: '',
        reason: ''
    });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (isOpen && data) {
            setFormData({
                message: data.message,
                label: data.label,
                code: data.code,
                category: '기타 정상',
                reason: data.reason || ''
            });
            setError(null);
        }
    }, [isOpen, data]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        try {
            await onSave(formData);
            onClose();
        } catch (err: any) {
            const msg = err.response?.data?.detail || err.message || '저장에 실패했습니다.';
            setError(msg);
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen || !data) return null;

    return (
        <div className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm z-[100] flex items-center justify-center p-4 animate-in fade-in duration-200">
            <div className="bg-white rounded-3xl border border-slate-200 w-full max-w-2xl shadow-2xl overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
                {/* Header */}
                <div className="flex items-center justify-between px-8 py-5 border-b border-slate-100 bg-white">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-indigo-600 rounded-xl flex items-center justify-center text-white shadow-lg shadow-indigo-200">
                            <Database size={20} />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-slate-900">RAG에 참조 사례 등록</h2>
                            <p className="text-xs text-slate-500 font-medium">분석 데이터 보정 및 학습용</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors">
                        <X size={20} className="text-slate-400" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-8 space-y-6 max-h-[75vh] custom-scrollbar">
                    {error && (
                        <div className="p-4 bg-rose-50 border border-rose-100 rounded-2xl flex items-center gap-3 text-rose-700 text-sm font-medium">
                            <AlertCircle size={18} />
                            {error}
                        </div>
                    )}

                    {/* Message (Readonly) */}
                    <div>
                        <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">메시지 원문</label>
                        <div className="p-4 bg-slate-50 border border-slate-100 rounded-2xl text-slate-700 text-sm leading-relaxed max-h-32 overflow-y-auto whitespace-pre-wrap">
                            {formData.message}
                        </div>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-6">
                        {/* Status Grid */}
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">판정</label>
                                <div className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold border ${formData.label === 'SPAM' ? 'bg-rose-50 text-rose-700 border-rose-100' : 'bg-emerald-50 text-emerald-700 border-emerald-100'
                                    }`}>
                                    {formData.label}
                                </div>
                            </div>
                            {formData.label === 'SPAM' && (
                                <div>
                                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">분류 코드</label>
                                    <span className="text-sm font-mono font-bold text-slate-700 bg-slate-50 border border-slate-200 px-2 py-1 rounded">
                                        {formData.code || '미지정'}
                                    </span>
                                </div>
                            )}
                        </div>

                        {/* Category */}
                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">카테고리 *</label>
                            <div className="flex flex-wrap gap-2 mb-3">
                                {(formData.label === 'SPAM' ? SPAM_CATEGORY_PRESETS : HAM_CATEGORY_PRESETS).map(cat => (
                                    <button
                                        key={cat}
                                        type="button"
                                        onClick={() => setFormData({ ...formData, category: cat })}
                                        className={`px-3 py-1.5 text-xs rounded-xl border transition-all ${formData.category === cat
                                            ? 'bg-indigo-600 border-indigo-600 text-white shadow-md shadow-indigo-100'
                                            : 'bg-white border-slate-200 text-slate-500 hover:border-slate-300'
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
                                className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:bg-white outline-none transition-all"
                                required
                            />
                        </div>

                        {/* Reason */}
                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">판단 근거 *</label>
                            <textarea
                                value={formData.reason}
                                onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
                                placeholder="예: 일반 광고로 판단되어 햄으로 처리"
                                className="w-full h-32 px-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-sm focus:ring-2 focus:ring-indigo-500 focus:bg-white outline-none transition-all resize-none"
                                required
                            />
                        </div>

                        {/* Actions */}
                        <div className="pt-2 flex gap-3">
                            <button
                                type="button"
                                onClick={onClose}
                                className="flex-1 py-4 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-2xl transition-all"
                            >
                                취소
                            </button>
                            <button
                                type="submit"
                                disabled={loading}
                                className="flex-[2] py-4 bg-slate-900 hover:bg-slate-800 text-white font-bold rounded-2xl transition-all shadow-xl shadow-slate-200 disabled:opacity-50 flex items-center justify-center gap-2"
                            >
                                {loading ? <RefreshCw className="animate-spin" size={20} /> : <Save size={20} />}
                                {loading ? '저장 중...' : '등록'}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
};
