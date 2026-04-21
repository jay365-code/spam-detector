import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, Save, RefreshCw, Settings, ShieldAlert, CheckCircle2, Zap } from 'lucide-react';

interface ConfigItem {
    key: string;
    label: string;
    description: string;
    type: 'select' | 'number' | 'boolean' | 'float' | 'model_select';
    options?: string[];
    min?: number;
    max?: number;
    step?: number;
}

interface SettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
}

// [Fix] Remote Server Compatibility: Use window.location.hostname for API
const API_BASE = `http://${window.location.hostname}:8000`;

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
    const [metadata, setMetadata] = useState<ConfigItem[]>([]);
    const [values, setValues] = useState<Record<string, any>>({});
    const [models, setModels] = useState<Record<string, any[]>>({});
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [quotaStatus, setQuotaStatus] = useState<Record<string, any>>({});
    const [quotaResetting, setQuotaResetting] = useState(false);
    const [quotaResetSuccess, setQuotaResetSuccess] = useState(false);
    const [pendingIndices, setPendingIndices] = useState<Record<string, number>>({});

    useEffect(() => {
        if (isOpen) {
            fetchConfig();
            fetchModels();
            fetchQuotaStatus();
        }
    }, [isOpen]);

    const fetchConfig = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/config`);
            const data = await res.json();
            setMetadata(data.metadata);
            setValues(data.values);
            setError(null);
        } catch (err) {
            console.error('Failed to fetch config:', err);
            setError(`백엔드 서버(${API_BASE})에 연결할 수 없습니다. (포트 8000 확인)`);
        } finally {
            setLoading(false);
        }
    };

    const fetchModels = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/models`);
            const data = await res.json();
            setModels(data);
        } catch (err) {
            console.error('Failed to fetch models:', err);
        }
    };

    const fetchQuotaStatus = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/config/quota-status`);
            const data = await res.json();
            if (data.success && data.quota_status) setQuotaStatus(data.quota_status);
        } catch (err) {
            console.error('Failed to fetch quota status:', err);
        }
    };

    const handleResetQuota = async (provider?: string) => {
        setQuotaResetting(true);
        setQuotaResetSuccess(false);
        try {
            const res = await fetch(`${API_BASE}/api/config/reset-quota`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(provider ? { provider } : {}),
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.message || '리셋 실패');
            await fetchQuotaStatus();
            // 리셋 성공 시 3초간 시각적 피드백 표시
            setQuotaResetSuccess(true);
            setTimeout(() => setQuotaResetSuccess(false), 3000);
        } catch (err) {
            console.error('Failed to reset quota:', err);
            alert('Quota 리셋에 실패했습니다.');
        } finally {
            setQuotaResetting(false);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        setSuccess(false);
        try {
            // 1. Save general settings
            const res = await fetch(`${API_BASE}/api/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings: values }),
            });
            if (!res.ok) throw new Error('Save failed');

            // 2. Save pending key indices if any
            if (Object.keys(pendingIndices).length > 0) {
                const resIdx = await fetch(`${API_BASE}/api/config/set-key-index`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ indices: pendingIndices }),
                });
                if (!resIdx.ok) throw new Error('Key index save failed');
                setPendingIndices({});
                await fetchQuotaStatus(); // Refresh to reflect new index/exhaustion state
            }

            setSuccess(true);
            setTimeout(() => setSuccess(false), 3000);
        } catch (err) {
            console.error('Failed to save config:', err);
            alert('설정 저장에 실패했습니다.');
        } finally {
            setSaving(false);
        }
    };

    if (!isOpen) return null;

    const renderInput = (item: ConfigItem) => {
        const val = values[item.key] ?? '';

        switch (item.type) {
            case 'select':
                return (
                    <select
                        value={val}
                        onChange={(e) => setValues({ ...values, [item.key]: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-white focus:ring-2 focus:ring-blue-500 outline-none"
                    >
                        {item.options?.map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                        ))}
                    </select>
                );
            case 'number':
            case 'float':
                return (
                    <input
                        type="number"
                        value={val}
                        min={item.min}
                        max={item.max}
                        step={item.step || 1}
                        onChange={(e) => setValues({ ...values, [item.key]: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-white focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                );
            case 'boolean':
                return (
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => setValues({ ...values, [item.key]: val === '1' ? '0' : '1' })}
                            className={`w-12 h-6 rounded-full transition-all relative flex items-center px-1 ${val === '1' ? "bg-blue-600" : "bg-slate-700"}`}
                        >
                            <div className={`w-4 h-4 bg-white rounded-full transition-transform shadow-sm ${val === '1' ? "translate-x-6" : "translate-x-0"}`} />
                        </button>
                        <span className="text-xs font-semibold text-slate-400">{val === '1' ? 'ON' : 'OFF'}</span>
                    </div>
                );
            case 'model_select':
                const provider = values['LLM_PROVIDER'];
                const providerModels = models[provider] || [];
                return (
                    <select
                        value={val}
                        onChange={(e) => setValues({ ...values, [item.key]: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-white focus:ring-2 focus:ring-blue-500 outline-none"
                    >
                        <option value="">모델 선택...</option>
                        {providerModels.map((m: any) => (
                            <option key={m.id} value={m.id}>{m.name}</option>
                        ))}
                    </select>
                );
            default:
                return (
                    <input
                        type="text"
                        value={val}
                        onChange={(e) => setValues({ ...values, [item.key]: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-white focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                );
        }
    };


    // [React Portal] Render modal at document.body level to avoid stacking context issues
    return createPortal(
        <div
            className="fixed inset-0 z-[99999] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200"
            onClick={(e) => {
                // Background click close
                if (e.target === e.currentTarget) onClose();
            }}
        >
            <div
                className="bg-slate-900 w-full max-w-xl rounded-3xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden border border-slate-800 animate-in zoom-in-95 duration-200"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="px-6 py-5 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-blue-500/10 text-blue-400 rounded-2xl flex items-center justify-center border border-blue-500/20">
                            <Settings size={20} />
                        </div>
                        <div>
                            <h2 className="text-lg font-bold text-white">Runtime Settings</h2>
                            <p className="text-xs text-slate-400 font-medium tracking-tight">Backend Environment Configuration</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-xl transition-colors text-slate-400">
                        <X size={20} />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-900/30 text-left">
                    {loading ? (
                        <div className="flex flex-col items-center justify-center py-20 gap-3 text-slate-500">
                            <RefreshCw size={32} className="animate-spin" />
                            <p className="text-sm font-medium">설정 로드 중...</p>
                        </div>
                    ) : error ? (
                        <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
                            <div className="w-16 h-16 bg-red-500/10 text-red-500 rounded-full flex items-center justify-center border border-red-500/20 mb-2">
                                <ShieldAlert size={32} />
                            </div>
                            <div className="space-y-1">
                                <p className="text-sm font-bold text-white">{error}</p>
                                <p className="text-xs text-slate-500 leading-relaxed px-10">
                                    서버가 꺼져있거나 네트워크 오류가 발생했습니다.<br />
                                    <code>backend/run.py</code> 실행 상태를 확인해주세요.
                                </p>
                            </div>
                            <button
                                onClick={() => { fetchConfig(); fetchModels(); }}
                                className="mt-2 px-6 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold rounded-xl border border-slate-700 transition-all flex items-center gap-2"
                            >
                                <RefreshCw size={14} />
                                다시 시도
                            </button>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 gap-6">
                            {metadata.map((item) => (
                                <div key={item.key} className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <label className="text-sm font-bold text-slate-300 flex items-center gap-1.5">
                                            {item.label}
                                            {values[item.key] === '***' && (
                                                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-500 border border-amber-500/30">PROTECTED</span>
                                            )}
                                        </label>
                                        <span className="text-[10px] font-mono text-slate-500 bg-slate-800/50 px-1.5 py-0.5 rounded uppercase tracking-wider">{item.key}</span>
                                    </div>
                                    {renderInput(item)}
                                    <p className="text-[11px] text-slate-500 font-medium leading-relaxed">{item.description}</p>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Quota 상태 패널: exhausted 여부에 따라 amber(경고) / emerald(정상) 동적 전환 */}
                    {(() => {
                        const hasExhausted = Object.values(quotaStatus).some(
                            (info: any) => typeof info === 'boolean' ? info : info?.exhausted
                        );
                        const isOk = !hasExhausted && Object.keys(quotaStatus).length > 0;
                        return (
                            <div className={`flex flex-col gap-3 rounded-2xl p-4 border transition-all duration-500 ${
                                quotaResetSuccess
                                    ? 'border-emerald-500/30 bg-emerald-500/5'
                                    : hasExhausted
                                        ? 'border-amber-500/20 bg-amber-500/5'
                                        : 'border-slate-700/50 bg-slate-800/30'
                            }`}>
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <Zap className={`shrink-0 transition-colors duration-500 ${
                                            quotaResetSuccess ? 'text-emerald-400' : hasExhausted ? 'text-amber-500' : 'text-slate-500'
                                        }`} size={18} />
                                        <span className={`text-xs font-bold transition-colors duration-500 ${
                                            quotaResetSuccess ? 'text-emerald-400' : hasExhausted ? 'text-amber-400' : 'text-slate-400'
                                        }`}>
                                            {quotaResetSuccess ? '✅ Quota 리셋 완료' : hasExhausted ? 'LLM Quota Exhausted' : 'LLM Quota 상태'}
                                        </span>
                                    </div>
                                    {isOk && !quotaResetSuccess && (
                                        <span className="text-[10px] font-bold text-emerald-500 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">정상</span>
                                    )}
                                </div>
                                <p className="text-[11px] text-slate-400 leading-relaxed">
                                    {quotaResetSuccess
                                        ? '모든 공급자의 Quota 플래그가 초기화되었습니다. LLM 호출이 재개됩니다.'
                                        : hasExhausted
                                            ? 'API quota 초과 시 모든 LLM 호출이 차단됩니다. 새 키를 추가했거나 시간이 지나면 아래 버튼으로 리셋하세요.'
                                            : 'API 키 인덱스를 수동으로 변경하거나 Quota 플래그를 강제 초기화할 수 있습니다.'
                                    }
                                </p>
                                <div className="flex flex-wrap items-center gap-2">
                                    {Object.entries(quotaStatus).map(([p, info]: [string, any]) => {
                                        const isExhausted = typeof info === 'boolean' ? info : info?.exhausted;
                                        const tot = info?.total || 1;
                                        const curIdx = pendingIndices[p] !== undefined ? pendingIndices[p] : (info?.current_index || 0);
                                        const dropdownOptions = Array.from({ length: tot }, (_, i) => i);
                                        return (
                                            <span
                                                key={p}
                                                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10.5px] font-bold ${
                                                    isExhausted
                                                        ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                                                        : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                                }`}
                                            >
                                                <span>{p}: {isExhausted ? '⚠ Exhausted' : '✓ OK'}</span>
                                                {tot > 1 ? (
                                                    <select
                                                        value={curIdx}
                                                        onChange={(e) => setPendingIndices({ ...pendingIndices, [p]: parseInt(e.target.value, 10) })}
                                                        className="opacity-90 font-mono tracking-tighter bg-black/40 px-1 py-0.5 rounded-sm text-[9px] outline-none cursor-pointer border hover:border-slate-500 border-transparent transition-colors"
                                                    >
                                                        {dropdownOptions.map(idx => (
                                                            <option key={idx} value={idx} className="bg-slate-800 text-white">
                                                                Key {idx + 1}/{tot}
                                                            </option>
                                                        ))}
                                                    </select>
                                                ) : (
                                                    tot >= 1 && <span className="opacity-75 font-mono tracking-tighter bg-black/20 px-1 py-0.5 rounded-sm text-[9px]">(Key {curIdx + 1}/{tot})</span>
                                                )}
                                            </span>
                                        );
                                    })}
                                </div>
                                <button
                                    onClick={() => handleResetQuota()}
                                    disabled={quotaResetting}
                                    className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                                        quotaResetting
                                            ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
                                            : hasExhausted
                                                ? 'bg-amber-600 hover:bg-amber-500 text-white'
                                                : 'bg-slate-700 hover:bg-slate-600 text-slate-300'
                                    }`}
                                >
                                    {quotaResetting ? <RefreshCw size={14} className="animate-spin" /> : <Zap size={14} />}
                                    {quotaResetting ? '리셋 중...' : 'Quota 리셋'}
                                </button>
                            </div>
                        );
                    })()}

                    <div className="bg-blue-500/5 rounded-2xl p-4 border border-blue-500/10 flex gap-3">
                        <ShieldAlert className="text-blue-500 shrink-0" size={18} />
                        <div className="space-y-1">
                            <p className="text-xs font-bold text-blue-400">주의 사항 & 팁</p>
                            <p className="text-[11px] text-slate-400 leading-relaxed font-medium">
                                • 변경된 설정은 백엔드 메모리에 즉시 반영되며, <code>.env</code> 파일에 영구 저장됩니다.
                            </p>
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="px-6 py-5 border-t border-slate-800 bg-slate-900/50 flex items-center justify-between">
                    <button
                        onClick={fetchConfig}
                        className="text-xs font-bold text-slate-400 hover:text-white flex items-center gap-1.5 px-3 py-2 rounded-xl hover:bg-slate-800 transition-all"
                    >
                        <RefreshCw size={14} />
                        Reset Defaults
                    </button>
                    <div className="flex items-center gap-3">
                        {success && (
                            <div className="flex items-center gap-1.5 text-emerald-400 text-xs font-bold animate-in fade-in slide-in-from-right-2">
                                <CheckCircle2 size={16} />
                                저장 완료!
                            </div>
                        )}
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className={`flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-bold transition-all shadow-lg active:scale-95 ${saving ? "bg-slate-800 text-slate-500 cursor-not-allowed" : "bg-blue-600 text-white hover:bg-blue-500 shadow-blue-500/20"
                                }`}
                        >
                            {saving ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
                            Save & Apply Changes
                        </button>
                    </div>
                </div>
            </div>
        </div>,
        document.body
    );
};
