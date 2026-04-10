import React, { useState, useEffect } from 'react';
import { X, Save, Trash2, Search, Link2, FileText, AlertTriangle, ShieldCheck, Database, CheckSquare, Square } from 'lucide-react';

interface DatabaseManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface UrlRecord {
  domain_path: string;
  status: string;
  hit_count: number;
  last_updated: string;
  created_at: string;
}

interface HistoryRecord {
  normalized_text: string;
  count: number;
  last_updated: string;
}

export const DatabaseManagerModal: React.FC<DatabaseManagerModalProps> = ({ isOpen, onClose }) => {
  const [activeTab, setActiveTab] = useState<'url' | 'history'>('url');
  
  // URL State
  const [urlRecords, setUrlRecords] = useState<UrlRecord[]>([]);
  const [urlSearch, setUrlSearch] = useState('');
  const [newUrl, setNewUrl] = useState('');
  
  // History State
  const [historyRecords, setHistoryRecords] = useState<HistoryRecord[]>([]);
  const [historySearch, setHistorySearch] = useState('');
  const [newHistoryText, setNewHistoryText] = useState('');
  const [newHistoryCount, setNewHistoryCount] = useState(1);
  
  // Loading & Prompt State
  const [loading, setLoading] = useState(false);
  const [promptData, setPromptData] = useState<{ isOpen: boolean; url: string; cleanPreview: string } | null>(null);

  // Selection State
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());

  // Clear selection when tab or search changes
  useEffect(() => {
    setSelectedItems(new Set());
  }, [activeTab, urlSearch, historySearch]);

  useEffect(() => {
    if (isOpen) {
      fetchData();
    }
  }, [isOpen, activeTab]);

  const fetchData = async () => {
    setLoading(true);
    try {
      if (activeTab === 'url') {
        const res = await fetch('http://localhost:8000/api/db/url-whitelist');
        const json = await res.json();
        if (json.success) setUrlRecords(json.data);
      } else {
        const res = await fetch('http://localhost:8000/api/db/spam-history');
        const json = await res.json();
        if (json.success) setHistoryRecords(json.data);
      }
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  const currentFilteredRecords = activeTab === 'url' 
    ? urlRecords.filter(r => r.domain_path.toLowerCase().includes(urlSearch.toLowerCase()))
    : historyRecords.filter(r => r.normalized_text.includes(historySearch));

  const handleToggleSelect = (id: string) => {
    const newSet = new Set(selectedItems);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelectedItems(newSet);
  };

  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      const allIds = currentFilteredRecords.map(r => activeTab === 'url' ? (r as UrlRecord).domain_path : (r as HistoryRecord).normalized_text);
      setSelectedItems(new Set(allIds));
    } else {
      setSelectedItems(new Set());
    }
  };

  const handleDeleteSelected = async () => {
    if (selectedItems.size === 0) return;
    if (!confirm(`선택한 ${selectedItems.size}개의 항목을 일괄 삭제하시겠습니까?`)) return;

    setLoading(true);
    const promises = Array.from(selectedItems).map(id => {
      const endpoint = activeTab === 'url' ? 'url-whitelist' : 'spam-history';
      return fetch(`http://localhost:8000/api/db/${endpoint}/${encodeURIComponent(id)}`, {
        method: 'DELETE'
      });
    });

    try {
      await Promise.all(promises);
      setSelectedItems(new Set());
      fetchData();
    } catch (err) {
      console.error("Bulk delete error", err);
    }
    setLoading(false);
  };

  // --- URL Handlers ---
  const handleAddUrl = async (urlToSave: string, raw: boolean) => {
    try {
      const res = await fetch('http://localhost:8000/api/db/url-whitelist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: urlToSave, raw })
      });
      if (res.ok) {
        setNewUrl('');
        setPromptData(null);
        fetchData();
      } else {
        alert("URL 추가 실패");
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleUrlSubmit = () => {
    if (!newUrl) return;
    try {
      const isHttp = newUrl.includes("://") ? newUrl : "http://" + newUrl;
      const urlObj = new URL(isHttp);
      const hasQuery = urlObj.search.length > 0;
      let domain = urlObj.hostname;
      if (domain.startsWith("www.")) domain = domain.substring(4);
      const cleanPreview = domain + urlObj.pathname.replace(/\/$/, "");
      
      if (hasQuery || newUrl.includes("www.")) {
        setPromptData({ isOpen: true, url: newUrl, cleanPreview });
      } else {
        handleAddUrl(newUrl, false);
      }
    } catch (e) {
      // Invalid URL parse, just try generic
      handleAddUrl(newUrl, false);
    }
  };

  const handleDeleteUrl = async (domainPath: string) => {
    if (!confirm(`'${domainPath}' 도메인을 화이트리스트에서 삭제하시겠습니까?`)) return;
    try {
      const res = await fetch(`http://localhost:8000/api/db/url-whitelist/${encodeURIComponent(domainPath)}`, {
        method: 'DELETE'
      });
      if (res.ok) fetchData();
    } catch (err) {}
  };

  // --- History Handlers ---
  const handleHistorySubmit = async () => {
    if (!newHistoryText) return;
    try {
      const res = await fetch('http://localhost:8000/api/db/spam-history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: newHistoryText, count: newHistoryCount })
      });
      if (res.ok) {
        setNewHistoryText('');
        setNewHistoryCount(1);
        fetchData();
      } else {
        alert("텍스트 추가 실패");
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteHistory = async (text: string) => {
    if (!confirm(`짧은 난독 텍스트를 삭제하시겠습니까?\n'${text}'`)) return;
    try {
      const res = await fetch(`http://localhost:8000/api/db/spam-history/${encodeURIComponent(text)}`, {
        method: 'DELETE'
      });
      if (res.ok) fetchData();
    } catch (err) {}
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-md flex items-center justify-center z-[100] p-4 text-slate-200 transition-opacity duration-300">
      <div className="bg-slate-900/90 backdrop-blur-3xl border border-slate-700/50 w-[96vw] max-w-[1400px] h-[86vh] rounded-2xl shadow-[0_0_50px_-12px_rgba(0,0,0,0.7)] flex flex-col overflow-hidden ring-1 ring-white/5">
        
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-white/5 bg-slate-800/20 relative z-20">
          <div className="flex items-center space-x-4">
            <div className="p-2.5 bg-gradient-to-br from-blue-500/20 to-indigo-500/20 rounded-xl border border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.2)] relative">
              <div className="absolute inset-0 bg-blue-400 blur-md opacity-20 rounded-xl"></div>
              <Database className="w-6 h-6 text-blue-400 relative z-10" />
            </div>
            <div>
              <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent">
                데이터베이스 관리자
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">Vanguard 3-Strike Cache & Whitelist System</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-800/80 hover:text-white rounded-xl transition-all duration-200 text-slate-400">
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* User Prompt Modal for URL Cleaning */}
        {promptData && (
          <div className="absolute inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-[200]">
            <div className="bg-slate-900/95 border border-slate-700 p-7 rounded-2xl max-w-lg w-full shadow-[0_0_60px_-15px_rgba(0,0,0,0.8)] ring-1 ring-white/10 transform transition-all scale-100 opacity-100">
              <div className="flex items-center space-x-3 text-amber-400 mb-5 pb-4 border-b border-slate-800">
                <AlertTriangle className="w-7 h-7 drop-shadow-[0_0_8px_rgba(251,191,36,0.4)]" />
                <h3 className="text-lg font-bold">도메인 정제 필요 확인</h3>
              </div>
              <p className="text-sm text-slate-300 mb-5 leading-relaxed">
                입력하신 URL에 파라미터나 불필요한 접두사(<span className="text-pink-400 font-semibold shadow-pink-500/20 drop-shadow-sm">?query...</span> 혹은 <span className="text-pink-400 font-semibold shadow-pink-500/20 drop-shadow-sm">www.</span>)가 포함되어 있습니다.<br/>
                범용적인 화이트리스트 적용을 위해 <strong>시스템 권장 형식</strong>으로 정제하여 저장하시겠습니까?
              </p>
              <div className="space-y-4 mb-8">
                <div className="bg-slate-950/50 p-4 rounded-xl border border-slate-800 flex flex-col gap-1.5 shadow-inner">
                  <span className="text-[11px] text-slate-500 uppercase font-bold tracking-wider">입력 원문</span>
                  <span className="text-sm text-slate-400 break-all font-mono">{promptData.url}</span>
                </div>
                <div className="bg-blue-950/30 p-4 rounded-xl border border-blue-900/50 flex flex-col gap-1.5 shadow-[inset_0_0_15px_rgba(59,130,246,0.05)] relative overflow-hidden">
                  <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500/50 shadow-[0_0_10px_rgba(59,130,246,0.5)]"></div>
                  <span className="text-[11px] text-blue-400 uppercase font-bold tracking-wider ml-1">시스템 권장 (추천)</span>
                  <span className="text-sm text-blue-200 break-all font-mono ml-1">{promptData.cleanPreview}</span>
                </div>
              </div>
              <div className="flex justify-end space-x-3">
                <button onClick={() => setPromptData(null)} className="px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-sm font-semibold transition-all shadow-sm">
                  취소
                </button>
                <button onClick={() => handleAddUrl(promptData.url, true)} className="px-5 py-2.5 rounded-xl border border-slate-600 hover:bg-slate-800 hover:border-slate-500 text-sm font-semibold transition-all shadow-sm text-slate-300">
                  원문 그대로 저장
                </button>
                <button onClick={() => handleAddUrl(promptData.url, false)} className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 shadow-[0_0_15px_rgba(59,130,246,0.3)] border border-blue-500/50 text-white text-sm font-bold transition-all transform hover:-translate-y-0.5 active:translate-y-0">
                  권장 형식으로 저장
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Body Layout */}
        <div className="flex flex-1 overflow-hidden">
          
          {/* Sidebar */}
          <div className="w-64 bg-slate-950/40 border-r border-slate-800/60 p-4 flex flex-col space-y-2 backdrop-blur-sm z-10">
            <button
              onClick={() => setActiveTab('url')}
              className={`flex items-center space-x-3 p-3.5 rounded-xl transition-all duration-300 group ${
                activeTab === 'url' ? 'bg-gradient-to-r from-blue-500/10 to-transparent text-blue-400 border-l-4 border-blue-500 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.05)]' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border-l-4 border-transparent'
              }`}
            >
              <ShieldCheck className={`w-5 h-5 transition-transform duration-300 ${activeTab === 'url' ? 'scale-110 drop-shadow-[0_0_8px_rgba(59,130,246,0.5)]' : 'group-hover:scale-110'}`} />
              <span className="font-semibold text-sm">URL 화이트리스트</span>
              <span className="ml-auto bg-black/30 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wider opacity-80 group-hover:opacity-100 transition-opacity shadow-inner">
                {urls.length}
              </span>
            </button>
            
            <button
              onClick={() => setActiveTab('history')}
              className={`flex items-center space-x-3 p-3.5 rounded-xl transition-all duration-300 group ${
                activeTab === 'history' ? 'bg-gradient-to-r from-pink-500/10 to-transparent text-pink-400 border-l-4 border-pink-500 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.05)]' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border-l-4 border-transparent'
              }`}
            >
              <FileText className={`w-5 h-5 transition-transform duration-300 ${activeTab === 'history' ? 'scale-110 drop-shadow-[0_0_8px_rgba(236,72,153,0.5)]' : 'group-hover:scale-110'}`} />
              <span className="font-semibold text-sm">짧은 난독 리스트</span>
              <span className="ml-auto bg-black/30 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wider opacity-80 group-hover:opacity-100 transition-opacity shadow-inner">
                {histories.length}
              </span>
            </button>
          </div>

          {/* Main Content Pane */}
          <div className="flex-1 flex flex-col bg-slate-900/30 relative">
            {/* Toolbar */}
            <div className="p-5 border-b border-slate-800/60 flex flex-wrap items-center justify-between gap-4 backdrop-blur-md bg-slate-900/40 z-10">
              
              {/* Left Group: Search & Selection Controls */}
              <div className="flex items-center space-x-3 flex-1 min-w-[320px]">
                <div className="relative flex-1 max-w-sm group">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 group-focus-within:text-blue-400 transition-colors" />
                <input
                  type="text"
                  placeholder={activeTab === 'url' ? "도메인 검색..." : "텍스트 검색..."}
                  value={activeTab === 'url' ? urlSearch : historySearch}
                  onChange={(e) => activeTab === 'url' ? setUrlSearch(e.target.value) : setHistorySearch(e.target.value)}
                  className="w-full bg-slate-950/60 border border-slate-700/80 rounded-xl pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all shadow-inner placeholder-slate-500 text-slate-200"
                />
              </div>

              {selectedItems.size > 0 && (
                <button 
                  onClick={handleDeleteSelected}
                  className="flex items-center space-x-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 px-4 py-2.5 rounded-xl text-sm font-bold transition-all shadow-[0_0_10px_rgba(239,68,68,0.1)] hover:shadow-[0_0_15px_rgba(239,68,68,0.2)] transform active:scale-95 whitespace-nowrap mr-2"
                >
                  <Trash2 className="w-4 h-4" />
                  <span>선택 삭제 ({selectedItems.size})</span>
                </button>
              )}
              </div>

              {/* Right Group: Add New Forms */}
              {activeTab === 'url' ? (
                <div className="flex items-center space-x-2.5">
                  <input
                    type="text"
                    placeholder="https://lotteon.com/xxx"
                    value={newUrl}
                    onChange={(e) => setNewUrl(e.target.value)}
                    className="w-80 bg-slate-950/60 border border-slate-700/80 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 shadow-inner placeholder-slate-500 transition-all font-mono"
                    onKeyDown={(e) => e.key === 'Enter' && handleUrlSubmit()}
                  />
                  <button onClick={handleUrlSubmit} className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 border border-blue-500/30 shadow-[0_0_15px_rgba(59,130,246,0.25)] hover:shadow-[0_0_20px_rgba(59,130,246,0.4)] px-5 py-2.5 rounded-xl text-sm font-bold text-white transition-all transform active:scale-95 whitespace-nowrap relative overflow-hidden group">
                    <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out z-0"></div>
                    <span className="relative z-10">신규 도메인 추가</span>
                  </button>
                </div>
              ) : (
                <div className="flex items-center space-x-2.5">
                  <input
                    type="text"
                    placeholder="스팸 문구 또는 텍스트..."
                    value={newHistoryText}
                    onChange={(e) => setNewHistoryText(e.target.value)}
                    className="w-64 bg-slate-950/60 border border-slate-700/80 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-pink-500/50 focus:border-pink-500/50 shadow-inner placeholder-slate-500 transition-all"
                    onKeyDown={(e) => e.key === 'Enter' && handleHistorySubmit()}
                  />
                  <input
                    type="number"
                    min="1"
                    value={newHistoryCount}
                    onChange={(e) => setNewHistoryCount(parseInt(e.target.value) || 1)}
                    className="w-20 bg-slate-950/60 border border-slate-700/80 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-pink-500/50 focus:border-pink-500/50 text-center shadow-inner font-mono font-bold text-pink-400"
                    title="누적 카운트"
                  />
                  <button onClick={handleHistorySubmit} className="bg-gradient-to-r from-pink-600 to-rose-600 hover:from-pink-500 hover:to-rose-500 border border-pink-500/30 shadow-[0_0_15px_rgba(236,72,153,0.25)] hover:shadow-[0_0_20px_rgba(236,72,153,0.4)] px-5 py-2.5 rounded-xl text-sm font-bold text-white transition-all transform active:scale-95 whitespace-nowrap relative overflow-hidden group">
                    <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out z-0"></div>
                    <span className="relative z-10">스팸 텍스트 추가</span>
                  </button>
                </div>
              )}
            </div>

            {/* Table Area */}
            <div className="flex-1 overflow-auto p-2 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
              {loading ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 gap-3">
                  <div className="animate-spin w-8 h-8 border-2 border-t-transparent border-blue-500 rounded-full" />
                  <span className="font-semibold tracking-wider text-sm animate-pulse">데이터 로딩 중...</span>
                </div>
              ) : (
                <table className="w-full text-left border-collapse">
                  <thead className="sticky top-0 z-10 bg-slate-900/90 backdrop-blur-md shadow-sm border-b border-slate-800">
                    <tr className="text-xs uppercase tracking-wider text-slate-400 group transition-colors hover:bg-slate-800/20">
                      <th className="py-2.5 px-3 w-12 text-center rounded-tl-lg">
                        <button 
                          onClick={() => handleSelectAll({ target: { checked: !(currentFilteredRecords.length > 0 && selectedItems.size === currentFilteredRecords.length) } } as any)}
                          className={`focus:outline-none transition-all duration-200 active:scale-90 ${(currentFilteredRecords.length > 0 && selectedItems.size === currentFilteredRecords.length) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}
                        >
                          {currentFilteredRecords.length > 0 && selectedItems.size === currentFilteredRecords.length ? (
                            <CheckSquare className="w-5 h-5 text-blue-500 drop-shadow-[0_0_5px_rgba(59,130,246,0.5)] mx-auto" />
                          ) : (
                            <Square className="w-5 h-5 text-slate-500 hover:text-slate-400 mx-auto" />
                          )}
                        </button>
                      </th>
                      <th className="py-2.5 px-3 font-semibold">
                        {activeTab === 'url' ? '도메인 경로 (Domain Path)' : '정규화된 텍스트 (Normalized Text)'}
                      </th>
                      <th className="py-2.5 px-3 font-semibold text-center w-24">
                        {activeTab === 'url' ? '통과 횟수' : '누적 카운트'}
                      </th>
                      <th className="py-2.5 px-3 font-semibold w-40">최근 업데이트</th>
                      <th className="py-2.5 px-3 font-semibold w-20 text-center rounded-tr-lg">관리</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 text-sm">
                    {activeTab === 'url' ? (
                      (currentFilteredRecords as UrlRecord[])
                        .map((row) => (
                        <tr key={row.domain_path} className={`hover:bg-slate-800/40 transition-colors group ${selectedItems.has(row.domain_path) ? 'bg-blue-500/10' : ''}`}>
                          <td className={`py-1.5 px-3 text-center border-l-2 relative ${selectedItems.has(row.domain_path) ? 'border-blue-500' : 'border-transparent'}`}>
                            <button 
                              onClick={() => handleToggleSelect(row.domain_path)}
                              className={`focus:outline-none transition-all duration-200 active:scale-90 ${selectedItems.has(row.domain_path) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}
                            >
                              {selectedItems.has(row.domain_path) ? (
                                <CheckSquare className="w-4 h-4 text-blue-500 drop-shadow-[0_0_5px_rgba(59,130,246,0.5)] mx-auto" />
                              ) : (
                                <Square className="w-4 h-4 text-slate-600 hover:text-slate-500 mx-auto" />
                              )}
                            </button>
                          </td>
                          <td className="py-1.5 px-3">
                            <div className="flex items-center space-x-2">
                              <div className="p-1 max-w-fit bg-blue-500/10 rounded-md">
                                <Link2 className="w-3.5 h-3.5 text-blue-400" />
                              </div>
                              <span className="text-slate-200 font-medium break-all font-mono text-[13px]">{row.domain_path}</span>
                              {row.status === 'SAFE' && <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0 rounded-full uppercase font-bold tracking-wider shadow-[0_0_8px_rgba(16,185,129,0.1)]">SAFE</span>}
                            </div>
                          </td>
                          <td className="py-1.5 px-3 text-center">
                            <span className="inline-flex items-center justify-center min-w-[2.2rem] h-6 px-1 bg-slate-950 border border-slate-800 text-blue-400 rounded p-0 font-mono text-xs font-bold shadow-inner">
                              {row.hit_count}
                            </span>
                          </td>
                          <td className="py-1.5 px-3 text-slate-500 text-xs whitespace-nowrap font-mono tracking-tight">
                            {row.last_updated}
                          </td>
                          <td className="py-1.5 px-3 text-center">
                            <button 
                              onClick={() => handleDeleteUrl(row.domain_path)}
                              className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all duration-200 opacity-0 group-hover:opacity-100 transform hover:scale-105"
                              title="삭제"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      ))
                    ) : (
                      (currentFilteredRecords as HistoryRecord[])
                        .map((row) => (
                        <tr key={row.normalized_text} className={`hover:bg-slate-800/40 transition-colors group ${selectedItems.has(row.normalized_text) ? 'bg-pink-500/10' : ''}`}>
                          <td className={`py-2 px-3 text-center align-top pt-2.5 border-l-2 relative ${selectedItems.has(row.normalized_text) ? 'border-pink-500' : 'border-transparent'}`}>
                            <button 
                              onClick={() => handleToggleSelect(row.normalized_text)}
                              className={`focus:outline-none transition-all duration-200 active:scale-90 ${selectedItems.has(row.normalized_text) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}
                            >
                              {selectedItems.has(row.normalized_text) ? (
                                <CheckSquare className="w-4 h-4 text-pink-500 drop-shadow-[0_0_5px_rgba(236,72,153,0.5)] mx-auto" />
                              ) : (
                                <Square className="w-4 h-4 text-slate-600 hover:text-slate-500 mx-auto" />
                              )}
                            </button>
                          </td>
                          <td className="py-2 px-3">
                            <div className="flex items-start">
                              <span className="text-slate-200 font-medium break-all max-h-16 overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-slate-700 leading-relaxed text-[13px]">{row.normalized_text}</span>
                            </div>
                          </td>
                          <td className="py-2 px-3 text-center align-top pt-2">
                            <span className={`inline-flex items-center justify-center min-w-[2.2rem] h-6 px-1 bg-slate-950 rounded font-mono text-xs font-bold shadow-inner ${row.count >= 10 ? 'text-red-400 border border-red-500/30 shadow-[0_0_8px_rgba(239,68,68,0.2)]' : 'text-pink-400 border border-pink-500/20'}`}>
                              {row.count}
                            </span>
                          </td>
                          <td className="py-2 px-3 text-slate-500 text-xs whitespace-nowrap align-top pt-2 font-mono tracking-tight">
                            {row.last_updated}
                          </td>
                          <td className="py-2 px-3 text-center align-top">
                            <button 
                              onClick={() => handleDeleteHistory(row.normalized_text)}
                              className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all duration-200 opacity-0 group-hover:opacity-100 transform hover:scale-105"
                              title="삭제"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                    
                    {/* Empty States */}
                    {(activeTab === 'url' && currentFilteredRecords.length === 0) && (
                      <tr><td colSpan={5} className="p-12 text-center text-slate-500 font-medium tracking-wide">조건에 맞는 검색 결과가 없습니다.</td></tr>
                    )}
                    {(activeTab === 'history' && currentFilteredRecords.length === 0) && (
                      <tr><td colSpan={5} className="p-12 text-center text-slate-500 font-medium tracking-wide">조건에 맞는 검색 결과가 없습니다.</td></tr>
                    )}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
