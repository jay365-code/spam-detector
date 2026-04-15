import os
import re

file_path = "src/components/DatabaseManagerModal.tsx"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add states
state_addition = """  // History State
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
  const [urlTotal, setUrlTotal] = useState(0);"""

content = re.sub(
    r"  // URL State.*?const \[newHistoryCount, setNewHistoryCount\] = useState\(1\);",
    state_addition,
    content,
    flags=re.DOTALL
)

# 2. Replace fetchData and related logic
fetch_logic_old = """  // Clear selection when tab changes
  useEffect(() => {
    setSelectedItems(new Set());
    if (activeTab === 'signatures') {
      fetchSignatures();
    }
  }, [activeTab]);

  useEffect(() => {
    if (isOpen && activeTab !== 'signatures') {
      fetchData();
    }
    if (isOpen && activeTab === 'signatures') {
      fetchSignatures();
    }
  }, [isOpen, activeTab]);

  const fetchData = async () => {
    setLoading(true);
    try {
      if (activeTab === 'url') {
        const res = await fetch('http://localhost:8000/api/db/url-whitelist');
        const json = await res.json();
        if (json.success) setUrlRecords(json.data);
      } else if (activeTab === 'history') {
        const res = await fetch('http://localhost:8000/api/db/spam-history');
        const json = await res.json();
        if (json.success) setHistoryRecords(json.data);
      }
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  const fetchSignatures = async (page = sigPage, query = sigSearch) => {
    setLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/db/signatures?page=${page}&limit=500&q=${encodeURIComponent(query)}&sort=${sigSortCol}&order=${sigSortOrder}`);
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

  // Debounce search on signatures
  useEffect(() => {
    if (activeTab === 'signatures' && isOpen) {
      const timer = setTimeout(() => {
        setSigPage(1);
        fetchSignatures(1, sigSearch);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [sigSearch, sigSortCol, sigSortOrder]);

  const sortedUrlRecords = useMemo(() => {
    let sorted = [...urlRecords];
    sorted.sort((a, b) => {
      if (a[urlSort.key] < b[urlSort.key]) return urlSort.dir === 'asc' ? -1 : 1;
      if (a[urlSort.key] > b[urlSort.key]) return urlSort.dir === 'asc' ? 1 : -1;
      return 0;
    });
    return sorted.filter(r => r.domain_path.toLowerCase().includes(urlSearch.toLowerCase()));
  }, [urlRecords, urlSort, urlSearch]);

  const sortedHistoryRecords = useMemo(() => {
    let sorted = [...historyRecords];
    sorted.sort((a, b) => {
      if (a[historySort.key] < b[historySort.key]) return historySort.dir === 'asc' ? -1 : 1;
      if (a[historySort.key] > b[historySort.key]) return historySort.dir === 'asc' ? 1 : -1;
      return 0;
    });
    return sorted.filter(r => r.normalized_text.toLowerCase().includes(historySearch.toLowerCase()));
  }, [historyRecords, historySort, historySearch]);

  const currentFilteredRecords = activeTab === 'url' ? sortedUrlRecords : (activeTab === 'history' ? sortedHistoryRecords : signatureRecords);"""

fetch_logic_new = """  const fetchUrls = async (page = urlPage, query = urlSearch) => {
    setLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/db/url-whitelist?page=${page}&limit=500&q=${encodeURIComponent(query)}&sort=${urlSort.key}&order=${urlSort.dir}`);
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
      const res = await fetch(`http://localhost:8000/api/db/spam-history?page=${page}&limit=500&q=${encodeURIComponent(query)}&sort=${historySort.key}&order=${historySort.dir}`);
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
      const res = await fetch(`http://localhost:8000/api/db/signatures?page=${page}&limit=500&q=${encodeURIComponent(query)}&sort=${sigSortCol}&order=${sigSortOrder}`);
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

  // Clear selection and fetch on tab switch
  useEffect(() => {
    setSelectedItems(new Set());
    if (activeTab === 'url') fetchUrls();
    else if (activeTab === 'history') fetchHistory();
    else if (activeTab === 'signatures') fetchSignatures();
  }, [activeTab]);

  // Initial load
  useEffect(() => {
    if (isOpen) {
      if (activeTab === 'url' && urlRecords.length === 0) fetchUrls();
      else if (activeTab === 'history' && historyRecords.length === 0) fetchHistory();
      else if (activeTab === 'signatures' && signatureRecords.length === 0) fetchSignatures();
    }
  }, [isOpen]);

  // Debounces
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

  const currentFilteredRecords = activeTab === 'url' ? urlRecords : (activeTab === 'history' ? historyRecords : signatureRecords);"""

content = content.replace(fetch_logic_old, fetch_logic_new)

# Fix fetchData calls in handleDeleteSelected, handleAddUrl, handleDeleteUrl, handleHistorySubmit, handleDeleteHistory
content = content.replace("fetchData()", "activeTab === 'url' ? fetchUrls() : fetchHistory()")

# Replace URL badge
content = content.replace(
    "{urlRecords.length}",
    "{urlTotal}"
)

# Replace History badge
content = content.replace(
    "{historyRecords.length}",
    "{historyTotal}"
)

# Fix search result count top right
content = content.replace(
    "const currentFilteredRecords = activeTab === 'url' ? urlRecords : (activeTab === 'history' ? historyRecords : signatureRecords);",
    "const currentFilteredRecords = activeTab === 'url' ? urlRecords : (activeTab === 'history' ? historyRecords : signatureRecords);\n  const currentFilteredTotal = activeTab === 'url' ? urlTotal : (activeTab === 'history' ? historyTotal : sigTotal);"
)

content = content.replace(
    "{activeTab === 'signatures' ? sigTotal : currentFilteredRecords.length}",
    "{currentFilteredTotal}"
)

# Update Pagination Footer to be dynamic
old_footer = """            {/* Pagination Footer for Signatures */}
            {activeTab === 'signatures' && sigTotal > 0 && (
              <div className="bg-slate-900/80 border-t border-slate-800/60 p-3 flex justify-between items-center px-5">
                <span className="text-xs text-slate-400 tracking-wide font-medium">전체 <strong className="text-slate-200">{sigTotal}</strong> 건 중 {(sigPage-1)*500+1} ~ {Math.min(sigPage*500, sigTotal)} 출력</span>
                <div className="flex items-center space-x-1">
                  <button 
                    disabled={sigPage <= 1} 
                    onClick={() => setSigPage(p => Math.max(1, p - 1))}
                    className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 disabled:opacity-30 hover:bg-slate-700 text-sm font-semibold transition-all"
                  >
                    이전
                  </button>
                  <div className="px-3 py-1 bg-slate-950/50 rounded text-slate-300 font-mono text-sm border border-slate-800">
                    <strong className="text-purple-400">{sigPage}</strong> / {totalPages}
                  </div>
                  <button 
                    disabled={sigPage >= totalPages} 
                    onClick={() => setSigPage(p => Math.min(totalPages, p + 1))}
                    className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 disabled:opacity-30 hover:bg-slate-700 text-sm font-semibold transition-all"
                  >
                    다음
                  </button>
                </div>
              </div>
            )}"""

new_footer = """            {/* Dynamic Pagination Footer */}
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
                    <strong className={activeTab === 'url' ? 'text-blue-400' : (activeTab === 'history' ? 'text-pink-400' : 'text-purple-400')}>{currentPage}</strong> / {totalPages}
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
            )}"""

content = content.replace(old_footer, new_footer)

# Fix variables
fix_vars = """  if (!isOpen) return null;

  const currentTotal = activeTab === 'url' ? urlTotal : (activeTab === 'history' ? historyTotal : sigTotal);
  const currentPage = activeTab === 'url' ? urlPage : (activeTab === 'history' ? historyPage : sigPage);
  const totalPages = Math.ceil(currentTotal / 500) || 1;
  const setPage = activeTab === 'url' ? setUrlPage : (activeTab === 'history' ? setHistoryPage : setSigPage);"""

content = content.replace(
    "  if (!isOpen) return null;\n\n  const totalPages = Math.ceil(sigTotal / 500) || 1;",
    fix_vars
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applied.")
