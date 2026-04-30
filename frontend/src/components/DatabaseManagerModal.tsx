import React, { useState, useEffect } from 'react';
import { X, Trash2, Search, Link2, FileText, AlertTriangle, ShieldCheck, Database, CheckSquare, Square, Maximize2, Minimize2, ChevronUp, ChevronDown, Key, Copy, Upload, Unlink } from 'lucide-react';
import { API_BASE } from '../config';

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

interface ShortenerRecord {
  domain: string;
  source: string;
  created_at: string;
}

interface SignatureRecord {
  signature: string;
  byte_length: number;
  source: string;
  hit_count: number;
  created_at: string;
  last_hit: string | null;
}

const SortIcon = ({ col, currentSort }: { col: string, currentSort: {key: string, dir: string} }) => {
  if (currentSort.key !== col) return <ChevronDown className="w-3.5 h-3.5 opacity-20 inline-block ml-1" />;
  return currentSort.dir === 'asc' ? <ChevronUp className="w-3.5 h-3.5 text-blue-400 inline-block ml-1" /> : <ChevronDown className="w-3.5 h-3.5 text-blue-400 inline-block ml-1" />;
};

export const DatabaseManagerModal: React.FC<DatabaseManagerModalProps> = ({ isOpen, onClose }) => {
  const [activeTab, setActiveTab] = useState<'url' | 'history' | 'signatures' | 'shorteners'>('url');
  
  // History State
  const [historyRecords, setHistoryRecords] = useState<HistoryRecord[]>([]);
  const [historySearch, setHistorySearch] = useState('');
  const [newHistoryText, setNewHistoryText] = useState('');
  const [newHistoryCount, setNewHistoryCount] = useState(1);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyTotal, setHistoryTotal] = useState(0);

  // URL State
  const [urlRecords, setUrlRecords] = useState<UrlRecord[]>([]);
  const [urlSearch, setUrlSearch] = useState('');
  const [newUrl, setNewUrl] = useState('');
  const [urlPage, setUrlPage] = useState(1);
  const [urlTotal, setUrlTotal] = useState(0);
  
  // Signature State
  const [signatureRecords, setSignatureRecords] = useState<SignatureRecord[]>([]);
  const [newSignature, setNewSignature] = useState('');
  const [sigSearch, setSigSearch] = useState('');
  const [sigPage, setSigPage] = useState(1);
  const [sigTotal, setSigTotal] = useState(0);
  const [sigSortCol, setSigSortCol] = useState('hit_count');
  const [sigSortOrder, setSigSortOrder] = useState('desc');

  // Shortener State
  const [shortenerRecords, setShortenerRecords] = useState<ShortenerRecord[]>([]);
  const [shortenerSearch, setShortenerSearch] = useState('');
  const [newShortenerDomain, setNewShortenerDomain] = useState('');
  const [shortenerPage, setShortenerPage] = useState(1);
  const [shortenerTotal, setShortenerTotal] = useState(0);
  const [shortenerSort, setShortenerSort] = useState<{key: string, dir: 'asc'|'desc'}>({key: 'domain', dir: 'asc'});

  // Excel Import State
  const [importLoading, setImportLoading] = useState(false);
  const [importProgress, setImportProgress] = useState<{current: number; total: number} | null>(null);
  const [importResults, setImportResults] = useState<Array<{filename: string; total_inserted: number; total_ignored: number; sheets: Record<string, any>}> | null>(null);

  // Client-side Sort Config for URL and History
  const [urlSort, setUrlSort] = useState<{key: keyof UrlRecord, dir: 'asc'|'desc'}>({key: 'hit_count', dir: 'desc'});
  const [historySort, setHistorySort] = useState<{key: keyof HistoryRecord, dir: 'asc'|'desc'}>({key: 'count', dir: 'desc'});

  // Loading & Prompt State
  const [loading, setLoading] = useState(false);
  const [promptData, setPromptData] = useState<{ isOpen: boolean; url: string; cleanPreview: string } | null>(null);

  // Selection State
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());

  // Window State
  const [isMaximized, setIsMaximized] = useState(false);

  const fetchUrls = async (page = urlPage, query = urlSearch) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/db/url-whitelist?page=${page}&limit=500&q=${encodeURIComponent(query)}&sort=${urlSort.key}&order=${urlSort.dir}`);
      const json = await res.json();
      if (json.success) {
        setUrlRecords(json.data.data);
        setUrlTotal(json.data.total);
        setUrlPage(json.data.page);
      }
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  const fetchHistory = async (page = historyPage, query = historySearch) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/db/spam-history?page=${page}&limit=500&q=${encodeURIComponent(query)}&sort=${historySort.key}&order=${historySort.dir}`);
      const json = await res.json();
      if (json.success) {
        setHistoryRecords(json.data.data);
        setHistoryTotal(json.data.total);
        setHistoryPage(json.data.page);
      }
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  const fetchSignatures = async (page = sigPage, query = sigSearch) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/db/signatures?page=${page}&limit=500&q=${encodeURIComponent(query)}&sort=${sigSortCol}&order=${sigSortOrder}`);
      const json = await res.json();
      if (json.success) {
        setSignatureRecords(json.data.data);
        setSigTotal(json.data.total);
        setSigPage(json.data.page);
      }
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  const fetchShorteners = async (page = shortenerPage, query = shortenerSearch) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/db/shortener-domains?page=${page}&limit=500&q=${encodeURIComponent(query)}&sort=${shortenerSort.key}&order=${shortenerSort.dir}`);
      const json = await res.json();
      if (json.success) {
        setShortenerRecords(json.data.data);
        setShortenerTotal(json.data.total);
        setShortenerPage(json.data.page);
      }
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  // Clear selection and fetch on tab switch
  useEffect(() => {
    setTimeout(() => {
      setSelectedItems(new Set());
      if (activeTab === 'url') fetchUrls();
      else if (activeTab === 'history') fetchHistory();
      else if (activeTab === 'signatures') fetchSignatures();
      else if (activeTab === 'shorteners') fetchShorteners();
    }, 0);
  }, [activeTab]);

  // Initial load
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        if (activeTab === 'url' && urlRecords.length === 0) fetchUrls();
        else if (activeTab === 'history' && historyRecords.length === 0) fetchHistory();
        else if (activeTab === 'signatures' && signatureRecords.length === 0) fetchSignatures();
        else if (activeTab === 'shorteners' && shortenerRecords.length === 0) fetchShorteners();
      }, 0);
    }
  }, [isOpen]);

  // Debounce for shortener search & sort
  useEffect(() => {
    if (activeTab === 'shorteners' && isOpen) {
      const timer = setTimeout(() => { setShortenerPage(1); fetchShorteners(1, shortenerSearch); }, 500);
      return () => clearTimeout(timer);
    }
  }, [shortenerSearch, shortenerSort]);

  useEffect(() => {
    if (activeTab === 'shorteners' && isOpen) setTimeout(() => fetchShorteners(shortenerPage, shortenerSearch), 0);
  }, [shortenerPage]);

  // Debounces for Search & Sort
  useEffect(() => {
    if (activeTab === 'signatures' && isOpen) {
      const timer = setTimeout(() => { setSigPage(1); fetchSignatures(1, sigSearch); }, 500);
      return () => clearTimeout(timer);
    }
  }, [sigSearch, sigSortCol, sigSortOrder]);

  useEffect(() => {
    if (activeTab === 'url' && isOpen) {
      const timer = setTimeout(() => { setUrlPage(1); fetchUrls(1, urlSearch); }, 500);
      return () => clearTimeout(timer);
    }
  }, [urlSearch, urlSort]);

  useEffect(() => {
    if (activeTab === 'history' && isOpen) {
      const timer = setTimeout(() => { setHistoryPage(1); fetchHistory(1, historySearch); }, 500);
      return () => clearTimeout(timer);
    }
  }, [historySearch, historySort]);

  // Page Change Fetchers
  useEffect(() => {
    if (activeTab === 'signatures' && isOpen) setTimeout(() => fetchSignatures(sigPage, sigSearch), 0);
  }, [sigPage]);

  useEffect(() => {
    if (activeTab === 'url' && isOpen) setTimeout(() => fetchUrls(urlPage, urlSearch), 0);
  }, [urlPage]);

  useEffect(() => {
    if (activeTab === 'history' && isOpen) setTimeout(() => fetchHistory(historyPage, historySearch), 0);
  }, [historyPage]);

  const currentFilteredRecords = activeTab === 'url' ? urlRecords : (activeTab === 'history' ? historyRecords : (activeTab === 'shorteners' ? shortenerRecords : signatureRecords));
  const currentFilteredTotal = activeTab === 'url' ? urlTotal : (activeTab === 'history' ? historyTotal : (activeTab === 'shorteners' ? shortenerTotal : sigTotal));

  const currentPage = activeTab === 'url' ? urlPage : (activeTab === 'history' ? historyPage : (activeTab === 'shorteners' ? shortenerPage : sigPage));
  const totalPages = Math.ceil(currentFilteredTotal / 500) || 1;
  const setPage = (updater: React.SetStateAction<number>) => {
    if (activeTab === 'url') setUrlPage(updater);
    else if (activeTab === 'history') setHistoryPage(updater);
    else if (activeTab === 'shorteners') setShortenerPage(updater);
    else setSigPage(updater);
  };

  const handleToggleSelect = (id: string) => {
    const newSet = new Set(selectedItems);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelectedItems(newSet);
  };

  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      const allIds = currentFilteredRecords.map(r => {
        if (activeTab === 'url') return (r as UrlRecord).domain_path;
        if (activeTab === 'history') return (r as HistoryRecord).normalized_text;
        if (activeTab === 'shorteners') return (r as ShortenerRecord).domain;
        return (r as SignatureRecord).signature;
      });
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
      const endpoint = activeTab === 'url' ? 'url-whitelist' : (activeTab === 'history' ? 'spam-history' : (activeTab === 'shorteners' ? 'shortener-domains' : 'signatures'));
      // For signature, we need double encode if there are slashes, but standard encodeURIComponent is fine
      return fetch(`${API_BASE}/api/db/${endpoint}/${encodeURIComponent(id)}`, {
        method: 'DELETE'
      });
    });

    try {
      await Promise.all(promises);
      setSelectedItems(new Set());
      if (activeTab === 'signatures') fetchSignatures();
      else if (activeTab === 'url') fetchUrls();
      else if (activeTab === 'shorteners') fetchShorteners();
      else fetchHistory();
    } catch (err) {
      console.error("Bulk delete error", err);
    }
    setLoading(false);
  };

  // --- URL Handlers ---
  const handleAddUrl = async (urlToSave: string, raw: boolean) => {
    try {
      const res = await fetch(`${API_BASE}/api/db/url-whitelist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: urlToSave, raw })
      });
      if (res.ok) {
        setNewUrl('');
        setPromptData(null);
        if (activeTab === 'url') fetchUrls();
        else fetchHistory();
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
    } catch {
      handleAddUrl(newUrl, false);
    }
  };

  const handleDeleteUrl = async (domainPath: string) => {
    if (!confirm(`'${domainPath}' 도메인을 화이트리스트에서 삭제하시겠습니까?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/db/url-whitelist/${encodeURIComponent(domainPath)}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        if (activeTab === 'url') fetchUrls();
        else fetchHistory();
      }
    } catch (e) { console.debug("삭제 요청 무시:", e); }
  };

  // --- History Handlers ---
  const handleHistorySubmit = async () => {
    if (!newHistoryText) return;
    try {
      const res = await fetch(`${API_BASE}/api/db/spam-history`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: newHistoryText, count: newHistoryCount })
      });
      if (res.ok) {
        setNewHistoryText('');
        setNewHistoryCount(1);
        if (activeTab === 'url') fetchUrls();
        else fetchHistory();
      } else {
        alert("텍스트 추가 실패");
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteHistory = async (text: string) => {
    if (!confirm(`짧은 난독 텍스트를 삭제하시겠습니까?
'${text}'`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/db/spam-history/${encodeURIComponent(text)}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        if (activeTab === 'url') fetchUrls();
        else fetchHistory();
      }
    } catch (e) { console.debug("삭제 요청 무시:", e); }
  };

  // --- Shortener Handlers ---
  const handleAddShortener = async () => {
    if (!newShortenerDomain) return;
    try {
      const res = await fetch(`${API_BASE}/api/db/shortener-domains`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: newShortenerDomain })
      });
      if (res.ok) {
        setNewShortenerDomain('');
        fetchShorteners();
      } else {
        const json = await res.json();
        alert(json.detail || '추가 실패');
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteShortener = async (domain: string) => {
    if (!confirm(`'${domain}' 도메인을 삭제하시겠습니까?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/db/shortener-domains/${encodeURIComponent(domain)}`, {
        method: 'DELETE'
      });
      if (res.ok) fetchShorteners();
    } catch (e) { console.debug('삭제 요청 무시:', e); }
  };

  const handleAddSignature = async () => {
    if (!newSignature) return;
    try {
      const res = await fetch(`${API_BASE}/api/db/signatures`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signature: newSignature })
      });
      if (res.ok) {
        setNewSignature('');
        fetchSignatures();
      } else {
        const json = await res.json();
        alert(json.detail || '추가 실패');
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteSig = async (text: string) => {
    if (!confirm(`시그니처를 삭제하시겠습니까?
'${text}'`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/db/signatures/${encodeURIComponent(text)}`, {
        method: 'DELETE'
      });
      if (res.ok) fetchSignatures();
    } catch (e) { console.debug("삭제 요청 무시:", e); }
  };

  // 엑셀 다중 파일 임포트 핸들러
  const handleExcelImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    
    setImportLoading(true);
    setImportResults(null);
    const fileList = Array.from(files);
    const results: Array<{filename: string; total_inserted: number; total_ignored: number; sheets: Record<string, any>}> = [];
    
    // 파일을 순차적으로 처리 (서버 부하 방지)
    for (let i = 0; i < fileList.length; i++) {
      setImportProgress({ current: i + 1, total: fileList.length });
      const file = fileList[i];
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const res = await fetch(`${API_BASE}/api/db/signatures/import-excel`, {
          method: 'POST',
          body: formData,
        });
        const json = await res.json();
        if (json.success) {
          results.push({
            filename: json.filename || file.name,
            total_inserted: json.summary.total_inserted,
            total_ignored: json.summary.total_ignored,
            sheets: json.summary.sheets
          });
        } else {
          results.push({ filename: file.name, total_inserted: 0, total_ignored: 0, sheets: { error: json.detail || '처리 실패' } });
        }
      } catch (err) {
        console.error(`임포트 실패: ${file.name}`, err);
        results.push({ filename: file.name, total_inserted: 0, total_ignored: 0, sheets: { error: '네트워크 오류' } });
      }
    }
    
    setImportResults(results);
    setImportLoading(false);
    setImportProgress(null);
    fetchSignatures(); // 목록 새로고침
    e.target.value = ''; // input 초기화 (동일 파일 재선택 허용)
  };

  if (!isOpen) return null;


  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-md flex items-center justify-center z-[100] p-2 sm:p-4 text-slate-200 transition-opacity duration-300">
      <div className={`bg-slate-900/90 backdrop-blur-3xl border border-slate-700/50 flex flex-col overflow-hidden ring-1 ring-white/5 transition-all duration-300 ${isMaximized ? 'w-[100vw] h-[100vh] max-w-none rounded-none' : 'w-[98vw] max-w-[1400px] h-[96vh] rounded-2xl shadow-[0_0_50px_-12px_rgba(0,0,0,0.7)]'}`}>
        
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/5 bg-slate-800/20 relative z-20">
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
          <div className="flex items-center space-x-1">
            <button onClick={() => setIsMaximized(!isMaximized)} className="p-2 hover:bg-slate-800/80 hover:text-white rounded-lg transition-all duration-200 text-slate-400 group relative">
              {isMaximized ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-5 h-5" />}
            </button>
            <button onClick={onClose} className="p-2 hover:bg-slate-800/80 hover:text-red-400 rounded-lg transition-all duration-200 text-slate-400 group relative">
              <X className="w-5 h-5" />
            </button>
          </div>
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
          <div className="w-72 bg-slate-950/40 border-r border-slate-800/60 p-4 flex flex-col space-y-2 backdrop-blur-sm z-10 overflow-y-auto">
            <button
              onClick={() => setActiveTab('url')}
              className={`flex items-center space-x-3 p-3.5 rounded-xl transition-all duration-300 group ${
                activeTab === 'url' ? 'bg-gradient-to-r from-blue-500/10 to-transparent text-blue-400 border-l-4 border-blue-500 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.05)]' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border-l-4 border-transparent'
              }`}
            >
              <ShieldCheck className={`w-5 h-5 transition-transform duration-300 flex-shrink-0 ${activeTab === 'url' ? 'scale-110 drop-shadow-[0_0_8px_rgba(59,130,246,0.5)]' : 'group-hover:scale-110'}`} />
              <span className="font-semibold text-sm whitespace-nowrap flex-1 text-left">URL 화이트리스트</span>
              <span className="bg-black/30 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wider flex-shrink-0 opacity-80 group-hover:opacity-100 transition-opacity shadow-inner">
                {urlTotal}
              </span>
            </button>
            
            <button
              onClick={() => setActiveTab('history')}
              className={`flex items-center space-x-3 p-3.5 rounded-xl transition-all duration-300 group ${
                activeTab === 'history' ? 'bg-gradient-to-r from-pink-500/10 to-transparent text-pink-400 border-l-4 border-pink-500 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.05)]' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border-l-4 border-transparent'
              }`}
            >
              <FileText className={`w-5 h-5 transition-transform duration-300 flex-shrink-0 ${activeTab === 'history' ? 'scale-110 drop-shadow-[0_0_8px_rgba(236,72,153,0.5)]' : 'group-hover:scale-110'}`} />
              <span className="font-semibold text-sm whitespace-nowrap flex-1 text-left">짧은 난독 리스트</span>
              <span className="bg-black/30 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wider flex-shrink-0 opacity-80 group-hover:opacity-100 transition-opacity shadow-inner">
                {historyTotal}
              </span>
            </button>

            <button
              onClick={() => setActiveTab('signatures')}
              className={`flex items-center space-x-3 p-3.5 rounded-xl transition-all duration-300 group ${
                activeTab === 'signatures' ? 'bg-gradient-to-r from-purple-500/10 to-transparent text-purple-400 border-l-4 border-purple-500 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.05)]' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border-l-4 border-transparent'
              }`}
            >
              <Key className={`w-5 h-5 transition-transform duration-300 flex-shrink-0 ${activeTab === 'signatures' ? 'scale-110 drop-shadow-[0_0_8px_rgba(168,85,247,0.5)]' : 'group-hover:scale-110'}`} />
              <span className="font-semibold text-sm whitespace-nowrap flex-1 text-left">영구 시그니처</span>
              <span className="bg-black/30 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wider flex-shrink-0 opacity-80 group-hover:opacity-100 transition-opacity shadow-inner">
                {sigTotal}
              </span>
            </button>

            <button
              onClick={() => setActiveTab('shorteners')}
              className={`flex items-center space-x-3 p-3.5 rounded-xl transition-all duration-300 group ${
                activeTab === 'shorteners' ? 'bg-gradient-to-r from-amber-500/10 to-transparent text-amber-400 border-l-4 border-amber-500 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.05)]' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border-l-4 border-transparent'
              }`}
            >
              <Unlink className={`w-5 h-5 transition-transform duration-300 flex-shrink-0 ${activeTab === 'shorteners' ? 'scale-110 drop-shadow-[0_0_8px_rgba(245,158,11,0.5)]' : 'group-hover:scale-110'}`} />
              <span className="font-semibold text-sm whitespace-nowrap flex-1 text-left">단축 URL 도메인</span>
              <span className="bg-black/30 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wider flex-shrink-0 opacity-80 group-hover:opacity-100 transition-opacity shadow-inner">
                {shortenerTotal}
              </span>
            </button>
          </div>

          {/* Main Content Pane */}
          <div className="flex-1 flex flex-col bg-slate-900/30 relative">
            {/* Toolbar */}
            <div className="px-5 py-3 border-b border-slate-800/60 flex flex-wrap items-center justify-between gap-4 backdrop-blur-md bg-slate-900/40 z-10">
              
              {/* Left Group: Search & Selection Controls */}
              <div className="flex items-center space-x-3 flex-1 min-w-[320px]">
                <div className="relative flex-1 max-w-sm group">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 group-focus-within:text-blue-400 transition-colors" />
                  <input
                    type="text"
                    placeholder={activeTab === 'url' ? "도메인 검색..." : activeTab === 'history' ? "텍스트 검색..." : "전체 시그니처 검색 (서버 연동)"}
                    value={activeTab === 'url' ? urlSearch : activeTab === 'history' ? historySearch : activeTab === 'shorteners' ? shortenerSearch : sigSearch}
                    onChange={(e) => {
                      if (activeTab === 'url') setUrlSearch(e.target.value);
                      else if (activeTab === 'history') setHistorySearch(e.target.value);
                      else if (activeTab === 'shorteners') setShortenerSearch(e.target.value);
                      else setSigSearch(e.target.value);
                    }}
                    className="w-full bg-slate-950/60 border border-slate-700/80 rounded-lg pl-9 pr-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all shadow-inner placeholder-slate-500 text-slate-200"
                  />
                </div>
                
                <div className="flex items-center space-x-1.5 bg-black/20 px-2.5 py-1 rounded-md border border-slate-800/80 shadow-inner">
                  <span className="text-[11px] text-slate-500 font-bold uppercase tracking-wider">검색결과</span>
                  <span className="text-sm font-mono text-slate-200 font-bold">{currentFilteredTotal}</span>
                </div>
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

              {/* Right Group: Add New Forms */}
              {activeTab === 'url' ? (
                <div className="flex items-center space-x-2.5">
                  <input
                    type="text"
                    placeholder="https://lotteon.com/xxx"
                    value={newUrl}
                    onChange={(e) => setNewUrl(e.target.value)}
                    className="w-80 bg-slate-950/60 border border-slate-700/80 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 shadow-inner placeholder-slate-500 transition-all font-mono"
                    onKeyDown={(e) => e.key === 'Enter' && handleUrlSubmit()}
                  />
                  <button onClick={handleUrlSubmit} className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 border border-blue-500/30 shadow-[0_0_15px_rgba(59,130,246,0.25)] hover:shadow-[0_0_20px_rgba(59,130,246,0.4)] px-4 py-1.5 rounded-lg text-sm font-bold text-white transition-all transform active:scale-95 whitespace-nowrap relative overflow-hidden group">
                    <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out z-0"></div>
                    <span className="relative z-10">신규 추가</span>
                  </button>
                </div>
              ) : activeTab === 'history' ? (
                <div className="flex items-center space-x-2.5">
                  <input
                    type="text"
                    placeholder="스팸 문구 또는 텍스트..."
                    value={newHistoryText}
                    onChange={(e) => setNewHistoryText(e.target.value)}
                    className="w-64 bg-slate-950/60 border border-slate-700/80 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-pink-500/50 focus:border-pink-500/50 shadow-inner placeholder-slate-500 transition-all"
                    onKeyDown={(e) => e.key === 'Enter' && handleHistorySubmit()}
                  />
                  <input
                    type="number"
                    min="1"
                    value={newHistoryCount}
                    onChange={(e) => setNewHistoryCount(parseInt(e.target.value) || 1)}
                    className="w-16 bg-slate-950/60 border border-slate-700/80 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-pink-500/50 focus:border-pink-500/50 text-center shadow-inner font-mono font-bold text-pink-400"
                    title="누적 카운트"
                  />
                  <button onClick={handleHistorySubmit} className="bg-gradient-to-r from-pink-600 to-rose-600 hover:from-pink-500 hover:to-rose-500 border border-pink-500/30 shadow-[0_0_15px_rgba(236,72,153,0.25)] hover:shadow-[0_0_20px_rgba(236,72,153,0.4)] px-4 py-1.5 rounded-lg text-sm font-bold text-white transition-all transform active:scale-95 whitespace-nowrap relative overflow-hidden group">
                    <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out z-0"></div>
                    <span className="relative z-10">텍스트 추가</span>
                  </button>
                </div>
              ) : activeTab === 'signatures' ? (
                <div className="flex items-center space-x-2.5">
                  <input
                    type="text"
                    placeholder="새 시그니처 텍스트..."
                    value={newSignature}
                    onChange={(e) => setNewSignature(e.target.value)}
                    className="w-72 bg-slate-950/60 border border-slate-700/80 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 shadow-inner placeholder-slate-500 transition-all font-mono text-slate-200"
                    onKeyDown={(e) => e.key === 'Enter' && handleAddSignature()}
                  />
                  <button onClick={handleAddSignature} className="bg-gradient-to-r from-purple-600 to-violet-600 hover:from-purple-500 hover:to-violet-500 border border-purple-500/30 shadow-[0_0_15px_rgba(168,85,247,0.25)] hover:shadow-[0_0_20px_rgba(168,85,247,0.4)] px-4 py-1.5 rounded-lg text-sm font-bold text-white transition-all transform active:scale-95 whitespace-nowrap relative overflow-hidden group">
                    <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out z-0"></div>
                    <span className="relative z-10">개별 추가</span>
                  </button>
                  <label className="flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 shadow-sm px-4 py-1.5 rounded-lg text-sm font-bold text-slate-300 transition-all cursor-pointer transform active:scale-95 group relative overflow-hidden">
                    <div className="absolute inset-0 bg-white/5 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out z-0"></div>
                    <Upload className="w-4 h-4 relative z-10" />
                    <span className="relative z-10">엑셀 임포트</span>
                    <input type="file" accept=".xlsx" multiple hidden onChange={handleExcelImport} disabled={importLoading} />
                  </label>
                </div>
              ) : activeTab === 'shorteners' ? (
                <div className="flex items-center space-x-2.5">
                  <input
                    type="text"
                    placeholder="새 단축 URL 도메인 (예: short.kr)"
                    value={newShortenerDomain}
                    onChange={(e) => setNewShortenerDomain(e.target.value)}
                    className="w-72 bg-slate-950/60 border border-slate-700/80 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50 shadow-inner placeholder-slate-500 transition-all font-mono"
                    onKeyDown={(e) => e.key === 'Enter' && handleAddShortener()}
                  />
                  <button onClick={handleAddShortener} className="bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 border border-amber-500/30 shadow-[0_0_15px_rgba(245,158,11,0.25)] hover:shadow-[0_0_20px_rgba(245,158,11,0.4)] px-4 py-1.5 rounded-lg text-sm font-bold text-white transition-all transform active:scale-95 whitespace-nowrap relative overflow-hidden group">
                    <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out z-0"></div>
                    <span className="relative z-10">도메인 추가</span>
                  </button>
                </div>
              ) : null}
            </div>

            {/* Import Progress/Result Banner */}
            {importLoading && importProgress && (
              <div className="mx-2 mt-2 px-4 py-3 bg-purple-500/10 border border-purple-500/30 rounded-xl flex items-center space-x-3 animate-pulse">
                <div className="animate-spin w-5 h-5 border-2 border-t-transparent border-purple-400 rounded-full flex-shrink-0" />
                <span className="text-sm text-purple-300 font-semibold">
                  임포트 진행 중... ({importProgress.current}/{importProgress.total} 파일 처리 중)
                </span>
              </div>
            )}
            {importResults && !importLoading && (
              <div className="mx-2 mt-2 px-4 py-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl relative">
                <button onClick={() => setImportResults(null)} className="absolute top-2 right-2 p-1 text-slate-500 hover:text-slate-300 transition-colors rounded hover:bg-white/5">
                  <X className="w-4 h-4" />
                </button>
                <div className="flex items-center space-x-2 mb-2">
                  <span className="text-emerald-400 font-bold text-sm">✅ 임포트 완료</span>
                  <span className="text-xs text-slate-400">
                    (총 {importResults.reduce((s, r) => s + r.total_inserted, 0)}건 삽입, {importResults.reduce((s, r) => s + r.total_ignored, 0)}건 중복 무시)
                  </span>
                </div>
                <div className="space-y-1 max-h-32 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-700">
                  {importResults.map((r, i) => (
                    <div key={i} className="flex items-center justify-between text-xs px-2 py-1 bg-black/20 rounded-lg">
                      <span className="text-slate-300 font-mono truncate mr-4 flex-1">{r.filename}</span>
                      <div className="flex items-center space-x-3 flex-shrink-0">
                        <span className="text-emerald-400 font-bold">{r.total_inserted}건 삽입</span>
                        <span className="text-slate-500">/</span>
                        <span className="text-slate-400">{r.total_ignored}건 중복</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

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
                          onClick={() => handleSelectAll({ target: { checked: !(currentFilteredRecords.length > 0 && selectedItems.size === currentFilteredRecords.length) } } as unknown as React.ChangeEvent<HTMLInputElement>)}
                          className={`focus:outline-none transition-all duration-200 active:scale-90 ${(currentFilteredRecords.length > 0 && selectedItems.size === currentFilteredRecords.length) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}
                        >
                          {currentFilteredRecords.length > 0 && selectedItems.size === currentFilteredRecords.length ? (
                            <CheckSquare className="w-5 h-5 text-blue-500 drop-shadow-[0_0_5px_rgba(59,130,246,0.5)] mx-auto" />
                          ) : (
                            <Square className="w-5 h-5 text-slate-500 hover:text-slate-400 mx-auto" />
                          )}
                        </button>
                      </th>
                      {activeTab === 'url' && (
                        <>
                          <th className="py-2.5 px-3 font-semibold cursor-pointer hover:bg-white/5" onClick={() => setUrlSort({key: 'domain_path', dir: urlSort.key==='domain_path'&&urlSort.dir==='asc'?'desc':'asc'})}>
                            도메인 경로 (Domain Path) <SortIcon col="domain_path" currentSort={urlSort} />
                          </th>
                          <th className="py-2.5 px-3 font-semibold text-center w-24 cursor-pointer hover:bg-white/5" onClick={() => setUrlSort({key: 'hit_count', dir: urlSort.key==='hit_count'&&urlSort.dir==='asc'?'desc':'asc'})}>
                            통과 횟수 <SortIcon col="hit_count" currentSort={urlSort} />
                          </th>
                          <th className="py-2.5 px-3 font-semibold w-40 cursor-pointer hover:bg-white/5" onClick={() => setUrlSort({key: 'last_updated', dir: urlSort.key==='last_updated'&&urlSort.dir==='asc'?'desc':'asc'})}>
                            최근 업데이트 <SortIcon col="last_updated" currentSort={urlSort} />
                          </th>
                        </>
                      )}
                      {activeTab === 'history' && (
                        <>
                          <th className="py-2.5 px-3 font-semibold cursor-pointer hover:bg-white/5" onClick={() => setHistorySort({key: 'normalized_text', dir: historySort.key==='normalized_text'&&historySort.dir==='asc'?'desc':'asc'})}>
                            정규화된 텍스트 <SortIcon col="normalized_text" currentSort={historySort} />
                          </th>
                          <th className="py-2.5 px-3 font-semibold text-center w-24 cursor-pointer hover:bg-white/5" onClick={() => setHistorySort({key: 'count', dir: historySort.key==='count'&&historySort.dir==='asc'?'desc':'asc'})}>
                            누적 카운트 <SortIcon col="count" currentSort={historySort} />
                          </th>
                          <th className="py-2.5 px-3 font-semibold w-40 cursor-pointer hover:bg-white/5" onClick={() => setHistorySort({key: 'last_updated', dir: historySort.key==='last_updated'&&historySort.dir==='asc'?'desc':'asc'})}>
                            최근 업데이트 <SortIcon col="last_updated" currentSort={historySort} />
                          </th>
                        </>
                      )}
                      {activeTab === 'signatures' && (
                        <>
                          <th className="py-2.5 px-3 font-semibold whitespace-nowrap cursor-pointer hover:bg-white/5" onClick={() => { setSigSortOrder(sigSortCol==='signature'&&sigSortOrder==='asc'?'desc':'asc'); setSigSortCol('signature'); }}>
                            시그니처 패턴 <SortIcon col="signature" currentSort={{key: sigSortCol, dir: sigSortOrder}} />
                          </th>
                          <th className="py-2.5 px-3 font-semibold text-center w-24 whitespace-nowrap cursor-pointer hover:bg-white/5" onClick={() => { setSigSortOrder(sigSortCol==='byte_length'&&sigSortOrder==='asc'?'desc':'asc'); setSigSortCol('byte_length'); }}>
                            바이트 <SortIcon col="byte_length" currentSort={{key: sigSortCol, dir: sigSortOrder}} />
                          </th>
                          <th className="py-2.5 px-3 font-semibold text-center w-28 whitespace-nowrap cursor-pointer hover:bg-white/5" onClick={() => { setSigSortOrder(sigSortCol==='hit_count'&&sigSortOrder==='asc'?'desc':'asc'); setSigSortCol('hit_count'); }}>
                            적중(Hit) <SortIcon col="hit_count" currentSort={{key: sigSortCol, dir: sigSortOrder}} />
                          </th>
                          <th className="py-2.5 px-3 font-semibold w-40 whitespace-nowrap cursor-pointer hover:bg-white/5" onClick={() => { setSigSortOrder(sigSortCol==='created_at'&&sigSortOrder==='asc'?'desc':'asc'); setSigSortCol('created_at'); }}>
                            최근 업데이트 <SortIcon col="created_at" currentSort={{key: sigSortCol, dir: sigSortOrder}} />
                          </th>
                          <th className="py-2.5 px-3 font-semibold w-40 whitespace-nowrap cursor-pointer hover:bg-white/5" onClick={() => { setSigSortOrder(sigSortCol==='last_hit'&&sigSortOrder==='asc'?'desc':'asc'); setSigSortCol('last_hit'); }}>
                            마지막 HIT <SortIcon col="last_hit" currentSort={{key: sigSortCol, dir: sigSortOrder}} />
                          </th>
                        </>
                      )}
                      {activeTab === 'shorteners' && (
                        <>
                          <th className="py-2.5 px-3 font-semibold cursor-pointer hover:bg-white/5" onClick={() => setShortenerSort({key: 'domain', dir: shortenerSort.key==='domain'&&shortenerSort.dir==='asc'?'desc':'asc'})}>
                            도메인 <SortIcon col="domain" currentSort={shortenerSort} />
                          </th>
                          <th className="py-2.5 px-3 font-semibold text-center w-28 cursor-pointer hover:bg-white/5" onClick={() => setShortenerSort({key: 'source', dir: shortenerSort.key==='source'&&shortenerSort.dir==='asc'?'desc':'asc'})}>
                            소스 <SortIcon col="source" currentSort={shortenerSort} />
                          </th>
                          <th className="py-2.5 px-3 font-semibold w-40 cursor-pointer hover:bg-white/5" onClick={() => setShortenerSort({key: 'created_at', dir: shortenerSort.key==='created_at'&&shortenerSort.dir==='asc'?'desc':'asc'})}>
                            등록일 <SortIcon col="created_at" currentSort={shortenerSort} />
                          </th>
                        </>
                      )}
                      <th className="py-2.5 px-3 font-semibold w-20 text-center rounded-tr-lg">관리</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 text-sm">
                    {/* Render URL Rows */}
                    {activeTab === 'url' && (currentFilteredRecords as UrlRecord[]).map((row) => (
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
                            <a 
                              href={row.domain_path.startsWith('http') ? row.domain_path : `https://${row.domain_path}`}
                              target="_blank" 
                              rel="noopener noreferrer"
                              className="text-slate-200 hover:text-blue-400 font-medium break-all font-mono text-[13px] hover:underline transition-colors"
                            >
                              {row.domain_path}
                            </a>
                            <button
                              onClick={() => navigator.clipboard.writeText(row.domain_path)}
                              className="p-1 text-slate-500 hover:text-blue-400 opacity-0 group-hover:opacity-100 transition-all rounded hover:bg-white/5 active:scale-95"
                              title="클립보드 복사"
                            >
                              <Copy className="w-3.5 h-3.5" />
                            </button>
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
                    ))}

                    {/* Render History Rows */}
                    {activeTab === 'history' && (currentFilteredRecords as HistoryRecord[]).map((row) => (
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
                            <span className="flex-1 text-slate-200 font-medium break-all max-h-16 overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-slate-700 leading-relaxed text-[13px]">{row.normalized_text}</span>
                            <button
                              onClick={() => navigator.clipboard.writeText(row.normalized_text)}
                              className="p-1 text-slate-500 hover:text-pink-400 opacity-0 group-hover:opacity-100 transition-all rounded hover:bg-white/5 active:scale-95 flex-shrink-0"
                              title="클립보드 복사"
                            >
                              <Copy className="w-3.5 h-3.5" />
                            </button>
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
                    ))}

                    {/* Render Signature Rows */}
                    {activeTab === 'signatures' && (currentFilteredRecords as SignatureRecord[]).map((row) => (
                      <tr key={row.signature} className={`hover:bg-slate-800/40 transition-colors group ${selectedItems.has(row.signature) ? 'bg-purple-500/10' : ''}`}>
                        <td className={`py-1.5 px-3 text-center border-l-2 relative ${selectedItems.has(row.signature) ? 'border-purple-500' : 'border-transparent'}`}>
                          <button 
                            onClick={() => handleToggleSelect(row.signature)}
                            className={`focus:outline-none transition-all duration-200 active:scale-90 ${selectedItems.has(row.signature) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}
                          >
                            {selectedItems.has(row.signature) ? (
                              <CheckSquare className="w-4 h-4 text-purple-500 drop-shadow-[0_0_5px_rgba(168,85,247,0.5)] mx-auto" />
                            ) : (
                              <Square className="w-4 h-4 text-slate-600 hover:text-slate-500 mx-auto" />
                            )}
                          </button>
                        </td>
                        <td className="py-1.5 px-3">
                          <div className="flex items-center space-x-2">
                            <span className="text-slate-200 font-medium break-all font-mono text-[13px]">{row.signature}</span>
                            <button
                              onClick={() => navigator.clipboard.writeText(row.signature)}
                              className="p-1 text-slate-500 hover:text-purple-400 opacity-0 group-hover:opacity-100 transition-all rounded hover:bg-white/5 active:scale-95 flex-shrink-0"
                              title="클립보드 복사"
                            >
                              <Copy className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                        <td className="py-1.5 px-3 text-center text-slate-400 text-xs font-mono">{row.byte_length}</td>
                        <td className="py-1.5 px-3 text-center">
                          <span className="inline-flex items-center justify-center min-w-[2.2rem] h-6 px-1 bg-slate-950 border border-slate-800 text-purple-400 rounded p-0 font-mono text-xs font-bold shadow-inner">
                            {row.hit_count}
                          </span>
                        </td>
                        <td className="py-1.5 px-3 text-slate-500 text-xs whitespace-nowrap font-mono tracking-tight">
                          {row.created_at || '-'}
                        </td>
                        <td className="py-1.5 px-3 text-slate-500 text-xs whitespace-nowrap font-mono tracking-tight">
                          {row.last_hit || '-'}
                        </td>
                        <td className="py-1.5 px-3 text-center">
                          <button 
                            onClick={() => handleDeleteSig(row.signature)}
                            className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all duration-200 opacity-0 group-hover:opacity-100 transform hover:scale-105"
                            title="삭제"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}

                    {/* Render Shortener Rows */}
                    {activeTab === 'shorteners' && (currentFilteredRecords as ShortenerRecord[]).map((row) => (
                      <tr key={row.domain} className={`hover:bg-slate-800/40 transition-colors group ${selectedItems.has(row.domain) ? 'bg-amber-500/10' : ''}`}>
                        <td className={`py-1.5 px-3 text-center border-l-2 relative ${selectedItems.has(row.domain) ? 'border-amber-500' : 'border-transparent'}`}>
                          <button 
                            onClick={() => handleToggleSelect(row.domain)}
                            className={`focus:outline-none transition-all duration-200 active:scale-90 ${selectedItems.has(row.domain) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}
                          >
                            {selectedItems.has(row.domain) ? (
                              <CheckSquare className="w-4 h-4 text-amber-500 drop-shadow-[0_0_5px_rgba(245,158,11,0.5)] mx-auto" />
                            ) : (
                              <Square className="w-4 h-4 text-slate-600 hover:text-slate-500 mx-auto" />
                            )}
                          </button>
                        </td>
                        <td className="py-1.5 px-3">
                          <div className="flex items-center space-x-2">
                            <div className="p-1 max-w-fit bg-amber-500/10 rounded-md">
                              <Unlink className="w-3.5 h-3.5 text-amber-400" />
                            </div>
                            <span className="text-slate-200 font-medium break-all font-mono text-[13px]">{row.domain}</span>
                            <button
                              onClick={() => navigator.clipboard.writeText(row.domain)}
                              className="p-1 text-slate-500 hover:text-amber-400 opacity-0 group-hover:opacity-100 transition-all rounded hover:bg-white/5 active:scale-95 flex-shrink-0"
                              title="클립보드 복사"
                            >
                              <Copy className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                        <td className="py-1.5 px-3 text-center">
                          <span className={`text-[10px] px-1.5 py-0 rounded-full uppercase font-bold tracking-wider ${
                            row.source === 'manual' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                            row.source === 'builtin' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
                            'bg-slate-500/10 text-slate-400 border border-slate-500/20'
                          }`}>
                            {row.source}
                          </span>
                        </td>
                        <td className="py-1.5 px-3 text-slate-500 text-xs whitespace-nowrap font-mono tracking-tight">
                          {row.created_at || '-'}
                        </td>
                        <td className="py-1.5 px-3 text-center">
                          <button 
                            onClick={() => handleDeleteShortener(row.domain)}
                            className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all duration-200 opacity-0 group-hover:opacity-100 transform hover:scale-105"
                            title="삭제"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}

                    {/* Empty States */}
                    {currentFilteredRecords.length === 0 && !loading && (
                      <tr><td colSpan={6} className="p-12 text-center text-slate-500 font-medium tracking-wide">조건에 맞는 검색 결과가 없습니다.</td></tr>
                    )}
                  </tbody>
                </table>
              )}
            </div>
            
            {/* Dynamic Pagination Footer */}
            {currentFilteredTotal > 0 && (
              <div className="bg-slate-900/80 border-t border-slate-800/60 p-3 flex justify-between items-center px-5">
                <span className="text-xs text-slate-400 tracking-wide font-medium">전체 <strong className="text-slate-200">{currentFilteredTotal}</strong> 건 중 {(currentPage-1)*500+1} ~ {Math.min(currentPage*500, currentFilteredTotal)} 출력</span>
                <div className="flex items-center space-x-1">
                  <button 
                    disabled={currentPage <= 1} 
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 disabled:opacity-30 hover:bg-slate-700 text-sm font-semibold transition-all"
                  >
                    이전
                  </button>
                  <div className="px-3 py-1 bg-slate-950/50 rounded text-slate-300 font-mono text-sm border border-slate-800">
                    <strong className={activeTab === 'url' ? 'text-blue-400' : (activeTab === 'history' ? 'text-pink-400' : (activeTab === 'shorteners' ? 'text-amber-400' : 'text-purple-400'))}>{currentPage}</strong> / {totalPages}
                  </div>
                  <button 
                    disabled={currentPage >= totalPages} 
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 disabled:opacity-30 hover:bg-slate-700 text-sm font-semibold transition-all"
                  >
                    다음
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
