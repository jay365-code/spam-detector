import { useState, useEffect } from 'react';
import { X, Loader2, CheckCircle2, Edit3, ShieldAlert } from 'lucide-react';
import { API_BASE } from '../config';

interface SignatureRefinerModalProps {
  isOpen: boolean;
  onClose: () => void;
  reportFilename: string | null;
  onApplySuccess: () => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  logs?: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onApplyModified?: (modified: Record<string, any>) => void;
}

const HighlightMessage = ({ message, target }: { message: string, target: string }) => {
  if (!target || !message) return <>{message}</>;
  const pureTarget = target.replace(/\s/g, "");
  if (pureTarget.length === 0) return <>{message}</>;

  let resultParts: string[] = [];
  try {
    const escapeRegExp = (str: string) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regexStr = pureTarget.split('').map(char => escapeRegExp(char)).join('\\s*');
    const regex = new RegExp(`(${regexStr})`, 'i');
    resultParts = message.split(regex);
  } catch {
    // fallback
  }

  if (resultParts.length > 1) {
    return (
      <>
        {resultParts.map((p, i) => (
          i % 2 === 1 
            ? <span key={i} className="text-emerald-300 font-bold bg-emerald-950/80 px-0.5 rounded mx-px underline decoration-emerald-800/50">{p}</span>
            : <span key={i}>{p}</span>
        ))}
      </>
    );
  }

  return <>{message}</>;
};

export default function SignatureRefinerModal({ isOpen, onClose, reportFilename, onApplySuccess, logs: parentLogs, onApplyModified }: SignatureRefinerModalProps) {
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [clusters, setClusters] = useState<any[]>([]);
  const [errorMsg, setErrorMsg] = useState("");

  const getByteLength = (str: string | null | undefined) => {
    if (!str || typeof str !== 'string') return 0;
    // 운영자님 지시: 바이트 계산 시 공백은 무조건 제외하고 알맹이 길이만 잼
    const pureStr = str.replace(/\s/g, "");
    let len = 0;
    for (let i = 0; i < pureStr.length; i++) {
      len += pureStr.charCodeAt(i) > 127 ? 2 : 1;
    }
    return len;
  };

  const isValidByte = (len: number) => {
    return (len >= 9 && len <= 20) || (len >= 39 && len <= 40);
  };

  useEffect(() => {
    if (isOpen && reportFilename) {
      fetchScan();
    } else {
      setClusters([]);
      setErrorMsg("");
    }
  }, [isOpen, reportFilename]);

  const fetchScan = async () => {
    setLoading(true);
    setErrorMsg("");
    try {
      const res = await fetch(`${API_BASE}/api/reports/${encodeURIComponent(reportFilename!)}/refine-scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ logs: parentLogs || null })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to fetch scan');
      
      // 초기 렌더링용 매핑
      const mapped = (data.clusters || []).map((c: Record<string, unknown>) => ({
        ...c,
        proposed: null,
        selected: false,
        isLoading: true,
        editSignature: ""
      }));
      setClusters(mapped);
      setLoading(false); // 표를 조기 렌더링
      
      // 개별 분석 백그라운드 호출
      if (mapped.length > 0) {
        analyzeAll(mapped);
      }
    } catch (err: unknown) {
      const e = err as Error;
      setErrorMsg(e.message);
      setLoading(false);
    }
  };

  const analyzeAll = async (initialClusters: Record<string, unknown>[]) => {
    // LLM Rate Limit 방지를 위해 20개씩 청크(Batch) 단위 처리
    const CHUNK_SIZE = 20;
    for (let i = 0; i < initialClusters.length; i += CHUNK_SIZE) {
        const chunk = initialClusters.slice(i, i + CHUNK_SIZE);
        const promises = chunk.map(async (clusterObj, chunkIdx) => {
            const actualIndex = i + chunkIdx;
            try {
                const res = await fetch(`${API_BASE}/api/reports/${encodeURIComponent(reportFilename!)}/refine-analyze-single`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cluster_items: clusterObj.original_items })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Failed to analyze');
                
                setClusters(prev => {
                    const newC = [...prev];
                    newC[actualIndex] = {
                        ...newC[actualIndex],
                        proposed: data.proposed,
                        selected: data.selected,
                        isLoading: false,
                        editSignature: data.proposed?.signature || ""
                    };
                    return newC;
                });
            } catch (err: unknown) {
                const e = err as Error;
                setClusters(prev => {
                    const newC = [...prev];
                    newC[actualIndex] = {
                        ...newC[actualIndex],
                        proposed: { decision: "error", reason: e.message, signature: "" },
                        selected: false,
                        isLoading: false
                    };
                    return newC;
                });
            }
        });
        await Promise.allSettled(promises);
    }
  };

  const handleApply = async () => {
    if (!reportFilename) return;

    // === 바이트 규격 유효성 검사 ===
    let hasInvalid = false;
    for (const c of clusters) {
      if (c.selected) {
        if (!isValidByte(getByteLength(c.editSignature as string))) {
          hasInvalid = true; 
          break;
        }
      } else {
        const items = c.original_items as Array<{current_signature?: string}>;
        for (const item of items) {
          // 빈 시그니처는 아예 지우겠다는 뜻이므로 제외, 들어있는 텍스트만 검사
          if (item.current_signature && !isValidByte(getByteLength(item.current_signature))) {
             hasInvalid = true; 
             break;
          }
        }
      }
    }
    
    if (hasInvalid) {
      alert("⛔ 규격 초과/미달 오류\n\n모든 시그니처는 반드시 (9~20 바이트) 또는 (39~40 바이트) 중 하나를 만족해야 합니다.\n빨간색 표기(Bytes)가 뜬 입력란을 확인하고 수정해 주세요.");
      return;
    }

    setApplying(true);
    setErrorMsg("");
    
    try {
      const payload = clusters.map(c => ({
        original_items: c.original_items,
        selected: c.selected,
        proposed_signature: c.editSignature // 사용자가 수정한 폼 데이터
      }));

      const res = await fetch(`${API_BASE}/api/reports/${encodeURIComponent(reportFilename)}/refine-apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clusters: payload, logs: parentLogs || null })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to apply');
      
      // 인메모리 모드: 서버가 수정된 로그 엔트리를 반환한 경우 부모 상태 직접 업데이트
      if (data.modified_entries && onApplyModified) {
        onApplyModified(data.modified_entries);
      } else {
        onApplySuccess(); // 파일 기반 모드: 서버 리로드 위임
      }
      
      alert(`총 ${data.applied_clusters_count}개의 클러스터 시그니처 덮어쓰기 완료!`);
      onClose();
    } catch (err: unknown) {
      const e = err as Error;
      setErrorMsg(e.message);
    } finally {
      setApplying(false);
    }
  };

  const toggleSelect = (index: number) => {
    const newItems = [...clusters];
    newItems[index].selected = !newItems[index].selected;
    setClusters(newItems);
  };

  const updateSignature = (index: number, val: string) => {
    const newItems = [...clusters];
    newItems[index].editSignature = val;
    setClusters(newItems);
  };

  const updateOriginalSignature = (clusterIdx: number, itemIdx: number, val: string) => {
    const newItems = [...clusters];
    newItems[clusterIdx].original_items[itemIdx].current_signature = val;
    setClusters(newItems);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-indigo-500/30 rounded-2xl flex flex-col w-full max-w-6xl mx-4 shadow-2xl overflow-hidden max-h-[90vh]">
        
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-800 bg-slate-900/90 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-indigo-500/20 flex items-center justify-center text-indigo-400">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">✨ 시그니처 자동 정제 (LLM)</h2>
              <p className="text-xs text-slate-400 mt-1">
                타겟 파일: {reportFilename || "선택된 파일 없음"}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-xl text-slate-400 hover:text-white transition-colors">
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-900">
          {errorMsg && (
            <div className="mb-4 p-4 bg-rose-950/50 border border-rose-900/50 text-rose-300 rounded-xl flex items-center gap-3">
              <ShieldAlert className="w-5 h-5 shrink-0" />
              <p className="text-sm">{errorMsg}</p>
            </div>
          )}

          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 space-y-4">
              <Loader2 className="w-12 h-12 text-indigo-400 animate-spin" />
              <p className="text-slate-400">명탐정 LLM 요원이 보고서를 샅샅이 분석 중입니다...</p>
            </div>
          ) : clusters.length === 0 ? (
            <div className="flex items-center justify-center py-20 text-slate-500">
              정제할 파편화 클러스터가 없거나, 검토 완료된 깔끔한 상태입니다.
            </div>
          ) : (
            <div className="space-y-6">
              {clusters.map((cluster, idx) => {
                 const isUnextractable = cluster.proposed && cluster.proposed.decision === "unextractable";
                 const orig = cluster.original_items || [];
                 return (
                   <div key={idx} className={`p-5 rounded-2xl border transition-colors ${cluster.selected ? 'bg-slate-800/50 border-indigo-500/30' : 'bg-slate-900 border-slate-800 opacity-60'}`}>
                     
                     <div className="flex justify-between items-start mb-4">
                         <div className="flex items-center gap-3">
                           <input 
                               type="checkbox" 
                               checked={cluster.selected}
                               onChange={() => toggleSelect(idx)}
                               disabled={cluster.isLoading}
                               className="w-5 h-5 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0 focus:ring-offset-0 cursor-pointer disabled:opacity-50"
                           />
                           <div>
                             <div className="flex items-center gap-2">
                               <h3 className="text-slate-200 font-bold">Group #{idx + 1}</h3>
                               <p className={`text-[10px] px-2 py-0.5 rounded-full font-bold border ${cluster.isLoading ? 'bg-slate-800 text-slate-400 border-slate-700 animate-pulse' : cluster.selected ? 'bg-indigo-950/40 text-indigo-400 border-indigo-500/30' : 'bg-slate-800 text-slate-400 border-slate-700'}`}>
                                 {cluster.isLoading ? 'LLM 분석 진행 중...' : (cluster.selected ? '우측 시그니처 1개로 그룹 일괄 반영' : '통일 제외 / 좌측 개별 시그니처 유지')}
                               </p>
                             </div>
                             <p className="text-xs text-slate-500 mt-1">{orig.length}개 유사 메시지 포함</p>
                           </div>
                         </div>
                        {isUnextractable && (
                           <div className="px-3 py-1 bg-amber-950/50 border border-amber-900/50 rounded-lg text-amber-500 text-xs font-bold shrink-0">
                             포기 (Unextractable) 
                           </div>
                        )}
                     </div>

                     <div className="grid grid-cols-12 gap-6">
                        {/* 기존 메시지 목록 영역 */}
                        <div className="col-span-12 lg:col-span-6 space-y-2 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                           <p className="text-xs font-semibold text-slate-500 sticky top-0 bg-inherit pb-1">파편화된 원본 시그니처 이력</p>
                           {orig.slice(0, 5).map((o: any, i: number) => (
                             <div 
                               key={i} 
                               className={`text-[11px] bg-slate-950/50 p-3 rounded-xl border transition-all relative ${!cluster.selected ? 'border-indigo-500/50 shadow-sm bg-slate-900/40' : 'border-slate-800/50'}`}
                             >
                               <div 
                                 title="클릭하여 원문 메시지(공백 제거)를 우측 편집창에 붙여넣기"
                                 onClick={() => updateSignature(idx, o.message.replace(/\s/g, ""))}
                                 className="text-slate-300 break-words leading-relaxed cursor-pointer hover:text-indigo-400 transition-colors"
                               >
                                 <HighlightMessage message={o.message} target={cluster.selected ? cluster.editSignature : o.current_signature} />
                               </div>
                               
                               <div className="mt-2 pt-2 border-t border-slate-800/50 flex flex-col gap-1">
                                  <div className="flex items-center gap-2">
                                    <span className="text-rose-400 font-mono">{'➔'}</span>
                                    <input 
                                      type="text"
                                      disabled={cluster.selected}
                                      value={o.current_signature || ''}
                                      onChange={(e) => updateOriginalSignature(idx, i, e.target.value)}
                                      placeholder="개별 시그니처 텍스트"
                                      className={`flex-1 bg-transparent font-mono text-[11px] font-bold outline-none border-b border-transparent focus:border-indigo-500 transition-colors ${!cluster.selected ? 'text-emerald-400' : 'text-slate-500'}`}
                                      title="그룹 통일 체크박스를 해제하면 이 입력창을 개별적으로 수정할 수 있습니다."
                                    />
                                    <span className={`text-[9px] font-mono font-bold px-1.5 py-0.5 border rounded shrink-0 transition-colors ${!cluster.selected ? (isValidByte(getByteLength(o.current_signature)) ? 'bg-emerald-950/30 text-emerald-500 border-emerald-900' : 'bg-rose-950/30 text-rose-500 border-rose-900') : 'bg-transparent text-slate-600 border-transparent'}`}>
                                      {getByteLength(o.current_signature)} B
                                    </span>
                                  </div>
                               </div>
                             </div>
                           ))}
                           {orig.length > 5 && <div className="text-xs text-slate-500 text-center italic">+ {orig.length - 5} 더보기</div>}
                        </div>

                        {/* 신규 제안 영역 */}
                        <div className="col-span-12 lg:col-span-6 flex flex-col justify-end relative">
                           {/* 제외(통일 취소) 모드일 때 보여줄 오버레이 */}
                           {!cluster.isLoading && !cluster.selected && (
                             <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-950/70 backdrop-blur-[1px] rounded-xl border border-slate-800">
                                <div className="text-center">
                                  <div className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-slate-900 shadow-lg border border-slate-700 mb-3">
                                    <X className="w-5 h-5 text-slate-500" />
                                  </div>
                                  <p className="text-slate-300 font-bold text-sm">통일(대표) 구역 제외됨</p>
                                  <p className="text-slate-500 text-xs mt-1">좌측의 개별 시그니처 편집값을 유지합니다.</p>
                                </div>
                             </div>
                           )}

                           <div className={`bg-indigo-950/20 border border-indigo-900/30 p-4 rounded-xl relative h-full flex flex-col transition-all duration-300 ${!cluster.isLoading && !cluster.selected ? 'opacity-30 grayscale pointer-events-none blur-[1px]' : ''}`}>
                              {cluster.isLoading ? (
                                  <div className="flex-1 flex flex-col items-center justify-center space-y-3 py-6 opacity-60">
                                      <Loader2 className="w-8 h-8 text-indigo-400 animate-spin" />
                                      <p className="text-xs text-indigo-300 font-bold animate-pulse">명탐정 LLM 요원이 분석 중입니다...</p>
                                  </div>
                              ) : (
                                  <div className="flex-1 flex flex-col">
                                    {isUnextractable && (
                                      <div className="text-slate-400 text-xs mb-3 p-3 bg-amber-950/30 border border-amber-900/50 rounded-lg">
                                        <p className="font-bold text-amber-500/80 mb-1">⚠️ 유니크함 훼손 방지 (LLM 포기 제안)</p>
                                        <p className="opacity-80 leading-relaxed mb-1">{cluster.proposed ? cluster.proposed.reason : ""}</p>
                                        <p className="text-[9px] italic text-amber-500/70 border-t border-amber-900/50 pt-1 mt-1">
                                          * 체크박스를 켜고 직접 원문을 불러와 빈칸에 시그니처를 타이핑하여 강제 생성할 수도 있습니다.
                                        </p>
                                      </div>
                                    )}

                                    <div className="flex items-center justify-between mb-2">
                                      <p className="text-xs font-semibold text-indigo-400 flex items-center gap-1">
                                        <Edit3 className="w-3 h-3" /> 통일(대표) 시그니처 제안
                                      </p>
                                      <span className={`text-[10px] font-mono font-bold px-2 py-0.5 border rounded-full ${isValidByte(getByteLength(cluster.editSignature)) ? 'bg-emerald-950/50 text-emerald-400 border-emerald-800' : 'bg-rose-950/50 text-rose-400 border-rose-800'}`}>
                                        {getByteLength(cluster.editSignature)} bytes
                                      </span>
                                    </div>
                                    <textarea 
                                      rows={6}
                                      disabled={!cluster.selected}
                                      value={cluster.editSignature}
                                      onChange={(e) => updateSignature(idx, e.target.value)}
                                      placeholder="좌측의 메시지를 클릭하여 텍스트를 불러오거나 이곳에 직접 시그니처를 구성하세요."
                                      className="w-full bg-slate-950 text-emerald-400 font-mono font-bold text-sm border border-slate-700/50 rounded-lg px-3 py-3 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-30 resize-none overflow-y-auto custom-scrollbar"
                                    />
                                    {!isUnextractable && (
                                        <div className="text-xs text-slate-400 mt-3 pt-3 border-t border-slate-800/50 flex-1 flex flex-col gap-1 overflow-y-auto max-h-32 custom-scrollbar">
                                          <p className="font-bold shrink-0 opacity-70">LLM 사유:</p>
                                          <p className="leading-relaxed opacity-80 break-words">{cluster.proposed ? cluster.proposed.reason : ""}</p>
                                        </div>
                                    )}
                                  </div>
                              )}
                           </div>
                        </div>
                     </div>
                   </div>
                 );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-5 border-t border-slate-800 bg-slate-900/90 shrink-0">
          <button 
            onClick={onClose} 
            className="px-5 py-2.5 rounded-xl text-slate-300 font-medium hover:bg-slate-800 transition-colors"
          >
            취소
          </button>
          <button 
            onClick={handleApply}
            disabled={loading || applying || clusters.length === 0 || !clusters.every(c => !c.isLoading)}
            className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-bold rounded-xl shadow-lg transition-all flex items-center gap-2"
          >
            {applying ? <Loader2 className="w-5 h-5 animate-spin"/> : <CheckCircle2 className="w-5 h-5"/>}
            {applying ? '적용 중...' : '최종 덮어쓰기 (Confirm)'}
          </button>
        </div>
      </div>
    </div>
  );
}
