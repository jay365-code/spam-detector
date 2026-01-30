import { useState, useEffect, useRef } from 'react';
import { CheckCircle, AlertCircle, User, Database, Pencil, X, Save, Loader2, Search, FileText, FolderOpen } from 'lucide-react';
import { FileUpload } from './components/FileUpload';
import { StatusPanel } from './components/StatusPanel';
import { ChatInterface } from './components/ChatInterface';
import { RagManager } from './components/RagManager';

// 백엔드 constants.py 및 spam_guide.md v1.5 기준 (0-3 코드 체계)
const CLASSIFICATION_MAP: Record<string, string> = {
  "0": "기타 스팸 (통신, 대리운전, 구인/부업 등)",
  "1": "유해성 스팸 (성인, 불법 의약품, 나이트클럽 등)",
  "2": "사기/투자 스팸 (주식 리딩, 로또 등)",
  "3": "불법 도박/대출 (도박, 카지노, 불법 대출 등)",
  "30": "판단 보류 (HITL)",
  "HAM-1": "응답/알림/명세서",
  "HAM-2": "명확한 사업자 광고",
  "HAM-3": "생활 밀착형 정보/기타",
  "HAM-4": "간단 알림"
};

// 커스텀 MS Excel 아이콘 SVG (Fluent Design Style)
const ExcelIcon = ({ className }: { className?: string }) => (
  <svg
    viewBox="0 0 24 24"
    className={className}
    xmlns="http://www.w3.org/2000/svg"
  >
    {/* Background Document Shape */}
    <path
      d="M16 2H8C6.89543 2 6 2.89543 6 4V20C6 21.1046 6.89543 22 8 22H18C19.1046 22 20 21.1046 20 20V6L16 2Z"
      fill="#217346"
    />
    <path
      d="M16 2V6H20L16 2Z"
      fill="#107C41"
      opacity="0.5"
    />
    {/* Left Icon Box with 'X' */}
    <rect x="2" y="7" width="11" height="10" rx="1.5" fill="#107C41" />
    <path
      d="M5 10L9 14.5M9 10L5 14.5"
      stroke="white"
      strokeWidth="1.8"
      strokeLinecap="round"
    />
    {/* Subtle Grid Lines on the Right */}
    <rect x="14" y="9" width="4" height="1" rx="0.5" fill="white" opacity="0.3" />
    <rect x="14" y="11.5" width="4" height="1" rx="0.5" fill="white" opacity="0.3" />
    <rect x="14" y="14" width="4" height="1" rx="0.5" fill="white" opacity="0.3" />
  </svg>
);

const getCodeDescription = (rawCode?: string) => {
  if (!rawCode) return "";

  // 1. Try direct match
  if (CLASSIFICATION_MAP[rawCode]) {
    return `${rawCode}. ${CLASSIFICATION_MAP[rawCode]}`;
  }

  // 2. Try extracting number (for "1. Gambling" etc)
  const match = rawCode.match(/\d+/);
  if (match) {
    const num = match[0];
    // Avoid mapping HAM codes to SPAM descriptions if accidentally passed
    if (CLASSIFICATION_MAP[num] && !rawCode.toUpperCase().includes("HAM")) {
      return `${num}. ${CLASSIFICATION_MAP[num]}`;
    }
  }
  return `${rawCode}. 기타`;
};

// Helper to detect and linkify URLs
const formatMessageWithLinks = (text: string) => {
  if (!text) return "";
  const urlRegex = /((?:https?:\/\/|www\.|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})[^\s]*)/g;
  const parts = text.split(urlRegex);
  return parts.map((part, index) => {
    if (part.match(urlRegex)) {
      let href = part;
      if (!part.startsWith('http') && !part.startsWith('https')) {
        href = 'http://' + part;
      }
      return (
        <a
          key={index}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-400 hover:text-blue-300 underline break-all cursor-pointer relative z-10"
          onClick={(e) => e.stopPropagation()}
        >
          {part}
        </a>
      );
    }
    return part;
  });
};

function App() {
  const [clientId] = useState(() => 'client-' + Math.random().toString(36).substr(2, 9));
  const [logs, setLogs] = useState<any[]>([]);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [downloadFilename, setDownloadFilename] = useState<string | null>(null);

  // RAG Manager State
  const [isRagManagerOpen, setIsRagManagerOpen] = useState(false);
  const [ragInitialData, setRagInitialData] = useState<{
    message: string;
    label: 'SPAM' | 'HAM';
    code?: string;
    reason?: string;
  } | undefined>(undefined);

  // RAG 저장 모달 열기 (초기 데이터 포함)
  const openRagWithData = (message: string, isSpam: boolean, code?: string, reason?: string) => {
    setRagInitialData({
      message,
      label: isSpam ? 'SPAM' : 'HAM',
      code: code || '',
      reason: reason || ''
    });
    setIsRagManagerOpen(true);
  };

  // 결과 수정 모달 State
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingLog, setEditingLog] = useState<{
    index: number;
    message: string;
    is_spam: boolean;
    classification_code: string;
    reason: string;
    spam_probability: number;
  } | null>(null);
  const [editSaving, setEditSaving] = useState(false);

  // 수정 모달 열기
  const openEditModal = (logIndex: number, log: any) => {
    setEditingLog({
      index: logIndex,
      message: log.message,
      is_spam: log.result.is_spam,
      classification_code: log.result.classification_code || '',
      reason: log.result.reason || '',
      spam_probability: log.result.spam_probability || 0.95
    });
    setEditModalOpen(true);
  };

  // 수정 저장
  const saveEdit = async () => {
    if (!editingLog || !downloadFilename) return;

    setEditSaving(true);
    try {
      // 1. 백엔드 API로 엑셀 업데이트
      const response = await fetch('http://localhost:8000/api/excel/update-row', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: downloadFilename,
          message: editingLog.message,
          is_spam: editingLog.is_spam,
          classification_code: editingLog.classification_code,
          reason: editingLog.reason,
          spam_probability: editingLog.spam_probability
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Update failed');
      }

      // 2. UI 상태 업데이트
      setLogs(prev => {
        const newLogs = [...prev];
        if (newLogs[editingLog.index]) {
          newLogs[editingLog.index] = {
            ...newLogs[editingLog.index],
            result: {
              ...newLogs[editingLog.index].result,
              is_spam: editingLog.is_spam,
              classification_code: editingLog.classification_code,
              reason: editingLog.reason,
              spam_probability: editingLog.spam_probability
            }
          };
        }
        return newLogs;
      });

      setEditModalOpen(false);
      setEditingLog(null);
    } catch (error) {
      console.error('Edit save failed:', error);
      alert(`저장 실패: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setEditSaving(false);
    }
  };

  // Progress State
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [isProcessing, setIsProcessing] = useState(false);

  // HITL State
  const [hitlRequest, setHitlRequest] = useState<any | null>(null);

  // Resizable Panel State
  const [logHeight, setLogHeight] = useState(300);
  const [isDragging, setIsDragging] = useState(false);
  const [isConnected, setIsConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);

  // Filter & Search State
  const [logFilter, setLogFilter] = useState<'ALL' | 'SPAM' | 'HAM'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Report Management State
  const [activeReportName, setActiveReportName] = useState<string | null>(null);
  const [activeReportFileName, setActiveReportFileName] = useState<string | null>(null);
  const reportInputRef = useRef<HTMLInputElement>(null);

  // Load Report from Local File (Windows Explorer)
  const handleLocalLoadReport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const data = JSON.parse(event.target?.result as string);

        // Restore logs and associated filename
        setLogs(data.logs.map((l: any) => ({
          ...l,
          timestamp: l.timestamp ? new Date(l.timestamp) : new Date()
        })));
        setDownloadFilename(data.source_filename);
        if (data.source_filename) {
          setDownloadUrl(`http://localhost:8000/download/${encodeURIComponent(data.source_filename)}`);
        }
        setActiveReportName(data.report_name);
        setActiveReportFileName(file.name); // 원본 파일명 저장
        // Reset scroll and progress
        setProgress({ current: 0, total: 0 });

        // Reset input for same file re-selection
        if (reportInputRef.current) reportInputRef.current.value = '';
      } catch (error) {
        console.error('Load report error:', error);
        alert('올바르지 않은 보고서 형식입니다.');
      }
    };
    reader.readAsText(file);
  };

  const handleExcelSaveAs = async () => {
    if (!downloadUrl || !downloadFilename) return;

    try {
      // 리포트 파일명이 있으면 그걸 쓰고(.xlsx로 변경), 없으면 서버에서 준 파일명 사용
      const suggestedExcelName = activeReportFileName
        ? activeReportFileName.replace(/\.json$/i, ".xlsx")
        : downloadFilename;

      // 1. Fetch the file from server first (Include suggested name for header consistency)
      const fetchUrl = `${downloadUrl}${downloadUrl.includes('?') ? '&' : '?'}suggested_name=${encodeURIComponent(suggestedExcelName)}`;
      const response = await fetch(fetchUrl);
      const blob = await response.blob();

      // 2. Open Save File Picker
      if ('showSaveFilePicker' in window) {
        // @ts-ignore
        const handle = await window.showSaveFilePicker({
          suggestedName: suggestedExcelName,

          types: [{
            description: 'Excel File',
            accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] },
          }],
        });

        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
      } else {
        // Fallback
        const suggestedExcelName = activeReportFileName
          ? activeReportFileName.replace(/\.json$/i, ".xlsx")
          : downloadFilename;
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = suggestedExcelName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        console.error('Excel Save As failed:', err);
      }
    }
  };

  // Handle Save Report (Force Windows Save As Explorer)
  const handleDownloadReport = async () => {
    if (logs.length === 0) return;

    try {
      // 업로드된 파일명에서 날짜 패턴(20260101_A 등) 추출 시도
      let suggestedFileName = activeReportFileName;

      if (!suggestedFileName && downloadFilename) {
        const patternMatch = downloadFilename.match(/(\d{8}_[A-Z0-9]+)/);
        if (patternMatch) {
          suggestedFileName = `report-${patternMatch[1]}.json`;
        } else {
          const defaultBaseName = downloadFilename.replace(/\.[^/.]+$/, "").replace(/_gpt-.*$/, "");
          suggestedFileName = `report-${defaultBaseName}.json`;
        }
      }

      if (!suggestedFileName) {
        suggestedFileName = `report_${new Date().toISOString().slice(0, 10)}.json`;
      }


      // Attempt to use File System Access API for "Save As" dialog
      if ('showSaveFilePicker' in window) {
        // @ts-ignore
        const handle = await window.showSaveFilePicker({
          suggestedName: suggestedFileName,
          types: [{
            description: 'JSON Report',
            accept: { 'application/json': ['.json'] },
          }],
        });

        const reportData = {
          report_name: handle.name.replace(".json", ""),
          source_filename: downloadFilename || '',
          timestamp: new Date().toISOString(),
          logs: logs
        };

        const writable = await handle.createWritable();
        await writable.write(JSON.stringify(reportData, null, 2));
        await writable.close();

        // 새로 저장된 파일명을 현재 활성 파일명으로 업데이트
        setActiveReportFileName(handle.name);
      } else {
        // Fallback for browsers without showSaveFilePicker
        // suggestedFileName is guaranteed to be a string here
        const finalName = suggestedFileName as string;
        const reportData = {
          report_name: finalName.replace(".json", ""),
          source_filename: downloadFilename || '',
          timestamp: new Date().toISOString(),
          logs: logs
        };

        const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = finalName;

        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        console.error('Save failed:', err);
      }
    }
  };

  useEffect(() => {
    // No longer fetching from server as we use local Explorer
  }, []);

  // 스크롤 위치 감지
  const handleScroll = () => {
    if (logContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
      // 하단에서 10px 이내면 바닥에 있는 것으로 간주 (사용자가 위로 스크롤 시 즉시 감지하기 위함)
      const atBottom = scrollHeight - scrollTop - clientHeight < 10;
      setIsAtBottom(atBottom);
    }
  };

  // 새로운 로그 수신 시 하단 이동 (Smart Scroll)
  useEffect(() => {
    if (isAtBottom && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, isAtBottom]);

  // WebSocket Connection (Auto-Reconnect)
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: any;

    const connect = () => {
      console.log('Attempting WebSocket connection...');
      ws = new WebSocket(`ws://localhost:8000/ws/${clientId}`);

      ws.onopen = () => {
        console.log('Connected to WebSocket');
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('WS Message:', data);

        // Ignore Chat Streaming messages and Process Status for System Log
        if (data.type && (data.type.startsWith('CHAT_') || data.type === 'PROCESS_STATUS')) return;

        // Handle Progress/Log with Deduplication
        setLogs(prev => {
          // If this is a result message (has result), look for matching pending message
          if (data.result && data.message) {
            const index = prev.findIndex(l => l.message === data.message && !l.result);
            if (index !== -1) {
              // Found pending log -> matching result; Update it
              const newLogs = [...prev];
              newLogs[index] = { ...data, timestamp: newLogs[index].timestamp };
              return newLogs;
            }
          }

          // Safety check: Avoid adding exact duplicate results if already present
          const exists = prev.some(l =>
            l.message === data.message &&
            l.result && data.result &&
            l.result.reason === data.result.reason
          );
          if (exists) return prev;

          // Otherwise append new log
          return [...prev, { ...data, timestamp: new Date() }];
        });

        // Update Progress
        if (data.current !== undefined && data.total !== undefined) {
          setProgress({ current: data.current, total: data.total });
          if (data.current < data.total) {
            setIsProcessing(true);
          } else {
            setIsProcessing(false);
          }
        }

        // Detect HITL Request
        if (data.type === 'HITL_REQUEST') {
          console.log('HITL Request:', data);
          setHitlRequest(data);
          setIsProcessing(true);
        }
      };

      ws.onclose = () => {
        console.log('Disconnected. Retrying in 3s...');
        setIsConnected(false);
        wsRef.current = null;
        reconnectTimeout = setTimeout(connect, 3000);
      };

      wsRef.current = ws;
    };

    connect();

    return () => {
      if (ws) {
        ws.onclose = null;
        ws.onopen = null;
        ws.close();
      }
      clearTimeout(reconnectTimeout);
    };
  }, [clientId]);

  // Resizing Logic
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging) return;
      const newHeight = window.innerHeight - e.clientY;
      setLogHeight(Math.max(100, Math.min(newHeight, window.innerHeight - 200)));
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';
    } else {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = 'auto';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = 'auto';
    };
  }, [isDragging]);

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleUploadStart = () => {
    setLogs([]);
    setProgress({ current: 0, total: 0 });
    setIsProcessing(true);
    setDownloadUrl(null);
    setDownloadFilename(null);
    setHitlRequest(null);
    setActiveReportName(null); // 분석 시작 시 보고서 모드 해제
    setActiveReportFileName(null);
  };

  const handleUploadComplete = (filename: string) => {
    setIsProcessing(false);
    setDownloadFilename(filename);
    setDownloadUrl(`http://localhost:8000/download/${encodeURIComponent(filename)}`);
  };

  const handleHitlResponse = (decision: string, comment?: string) => {
    if (!wsRef.current || !hitlRequest) return;

    const responsePayload = {
      type: 'HITL_RESPONSE',
      decision: decision,
      comment: comment
    };

    wsRef.current.send(JSON.stringify(responsePayload));
    setHitlRequest(null);
    setIsProcessing(true);
  };

  const handleSendMessage = (message: string, mode: "TEXT" | "URL" | "Unified" | "IBSE") => {
    if (!wsRef.current) return;
    const msgPayload = {
      type: 'CHAT_MESSAGE',
      content: message,
      mode: mode // Include mode in payload
    };
    wsRef.current.send(JSON.stringify(msgPayload));
  };

  // Helper to parse reason text
  const parseReason = (reasonStr: string) => {
    if (!reasonStr) return { cleanReason: "", note: null, isManual: false };

    // Extract Reviewer Note
    const noteMatch = reasonStr.match(/\[Reviewer Note: (.*?)\]/);
    const note = noteMatch ? noteMatch[1] : null;

    // Check Manual Marker
    const isManual = reasonStr.includes("[Manually Marked");

    // Clean Reason
    let cleanReason = reasonStr
      .replace(/\[Reviewer Note: .*?\]/, '')
      .replace(/\[Manually Marked as .*?\]/, '')
      .trim();

    // Also remove Probability info from display if present (User requested clean LLM reason)
    cleanReason = cleanReason.replace(/\(Prob: .*?\)/, '').trim();

    return { cleanReason, note, isManual };
  };

  const handleClearChat = () => {
    // Optional: Logic to clear logs or reset other states if needed
    console.log("Chat cleared");
  };

  return (
    <div className="h-screen bg-slate-900 text-white flex flex-col overflow-hidden">

      {/* Background Ambience */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden z-0 pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-500/10 rounded-full blur-[100px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-500/10 rounded-full blur-[100px]" />
      </div>

      <div className="z-10 flex flex-col h-full relative">

        {/* TOP PANEL: File Upload & Status */}
        <div className="h-auto min-h-0 p-4 flex flex-col items-start justify-start relative bg-slate-900/50 backdrop-blur-sm shrink-0">
          <div className="flex items-center justify-between w-full mb-2 px-2">
            <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
              Spam Detector AI
            </h1>
            <button
              onClick={() => setIsRagManagerOpen(true)}
              className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg transition-colors text-sm"
            >
              <Database className="w-4 h-4 text-blue-400" />
              <span className="text-slate-300">스팸 RAG</span>
            </button>
          </div>

          <div className="w-full flex gap-6 items-start justify-center px-4">
            <div className="w-[500px] shrink-0">
              <FileUpload
                clientId={clientId}
                onUploadStart={handleUploadStart}
                onUploadComplete={handleUploadComplete}
                onFileSelect={() => {
                  setProgress({ current: 0, total: 0 });
                  setDownloadUrl(null);
                }}
              />
            </div>
            {((isProcessing || downloadUrl) && progress.total > 0) && (
              <div className="flex-1 max-w-sm min-w-[300px]">
                <StatusPanel
                  current={progress.current}
                  total={progress.total}
                  isProcessing={isProcessing}
                  downloadUrl={downloadUrl}
                  onDownload={handleExcelSaveAs}
                />
              </div>
            )}
          </div>
        </div>

        {/* MIDDLE PANEL: Chat Interface */}
        <div className="flex-1 p-4 relative min-h-0 overflow-hidden">
          <ChatInterface
            clientId={clientId}
            ws={wsRef.current}
            hitlRequest={hitlRequest}
            onHitlResponse={handleHitlResponse}
            onSendMessage={handleSendMessage}
            onClearChat={handleClearChat}
            isConnected={isConnected}
          />
        </div>

        {/* RESIZE HANDLE */}
        <div
          onMouseDown={handleMouseDown}
          className={`w-full h-1.5 cursor-row-resize bg-slate-800 hover:bg-blue-500 transition-colors z-50 flex items-center justify-center group ${isDragging ? 'bg-blue-500' : ''}`}
        >
          <div className="w-16 h-0.5 bg-slate-600 rounded-full group-hover:bg-blue-200 transition-colors" />
        </div>

        {/* BOTTOM PANEL: Log Viewer */}
        <div
          style={{ height: logHeight }}
          className="min-h-[100px] bg-black/40 overflow-hidden flex flex-col border-t border-slate-800 transition-[height] duration-0 ease-linear"
        >
          {/* Header */}
          <div className="px-4 py-3 bg-slate-800/80 border-b border-slate-700 flex items-center gap-4 text-xs font-mono select-none">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-blue-400" />
              <span className="text-sm font-bold text-slate-200">Spam Detection Report</span>
              {activeReportName && (
                <span className="px-2 py-0.5 bg-blue-500/20 text-blue-300 rounded text-[10px]">
                  Loaded: {activeReportName}
                </span>
              )}
            </div>

            {/* Filter Buttons */}
            <div className="flex items-center bg-slate-900/50 rounded-lg p-1 border border-slate-700 ml-4">
              {(['ALL', 'SPAM', 'HAM'] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setLogFilter(f)}
                  className={`px-3 py-1 rounded-md transition-all ${logFilter === f
                    ? 'bg-blue-500 text-white shadow-lg'
                    : 'text-slate-400 hover:text-slate-200'
                    }`}
                >
                  {f}
                </button>
              ))}
            </div>

            {/* Search Input */}
            <div className="relative flex-1 max-w-md ml-4">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
              <input
                type="text"
                placeholder="결과 내 검색..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-8 pr-8 py-1.5 text-slate-200 focus:outline-none focus:border-blue-500 transition-colors"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-slate-700 rounded"
                >
                  <X className="w-3.5 h-3.5 text-slate-400" />
                </button>
              )}
            </div>

            {/* Client Status */}
            <div className="flex items-center border-l border-slate-700 pl-4 ml-auto">
              <div
                className={`w-2.5 h-2.5 rounded-full ${isConnected ? 'bg-green-500 animate-pulse transition-colors' : 'bg-red-500 transition-colors'}`}
                title={isConnected ? 'Connected' : 'Offline'}
              />
            </div>


            {/* Report Actions */}
            <div className="flex items-center gap-2 ml-4">
              {/* 엑셀 다운로드는 '보고서 불러오기 후'에만 노출 */}
              {downloadUrl && activeReportName && (
                <button
                  onClick={handleExcelSaveAs}
                  className="p-2 hover:bg-slate-700 rounded-lg text-green-400 hover:text-green-300 transition-colors"
                  title="엑셀 결과 저장 (Save As)"
                >
                  <ExcelIcon className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={handleDownloadReport}
                disabled={logs.length === 0}
                className="p-2 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-blue-400 transition-colors disabled:opacity-50"
                title="리포트 저장 (JSON)"
              >
                <Save className="w-4 h-4" />
              </button>
              <button
                onClick={() => reportInputRef.current?.click()}
                className="p-2 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-purple-400 transition-colors"
                title="리포트 불러오기 (Open File)"
              >
                <FolderOpen className="w-4 h-4" />
                <input
                  type="file"
                  ref={reportInputRef}
                  onChange={handleLocalLoadReport}
                  accept=".json"
                  className="hidden"
                />
              </button>
            </div>
          </div>

          <div
            ref={logContainerRef}
            onScroll={handleScroll}
            className="flex-1 overflow-auto p-4 space-y-2"
          >
            {logs
              .map((log, originalIdx) => ({ ...log, originalIdx }))
              .filter(log => {
                // Apply Filter
                if (logFilter === 'SPAM' && (!log.result || !log.result.is_spam)) return false;
                if (logFilter === 'HAM' && (!log.result || log.result.is_spam)) return false;

                // Apply Search
                if (searchQuery.trim()) {
                  const query = searchQuery.toLowerCase();
                  const matchesMsg = log.message?.toLowerCase().includes(query);
                  const matchesReason = log.result?.reason?.toLowerCase().includes(query);
                  return matchesMsg || matchesReason;
                }
                return true;
              })
              .map((log) => {
                const { cleanReason, note, isManual } = log.result ? parseReason(log.result.reason) : { cleanReason: "", note: null, isManual: false };
                const idx = log.originalIdx;

                return (
                  <div key={idx} className="flex gap-3 items-start animate-fade-in group hover:bg-white/5 p-1 rounded font-mono text-sm">
                    <span className="text-slate-500 min-w-[30px] text-xs pt-1">
                      {String(idx + 1).padStart(3, '0')}
                    </span>

                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        {log.result ? (
                          <>
                            {log.result.is_spam ? (
                              <span className="text-red-400 flex items-center gap-1 bg-red-400/10 px-1.5 rounded text-xs font-bold whitespace-nowrap">
                                <CheckCircle className="w-3 h-3 invisible" /> {/* Placeholder to balance space if needed */}
                                <AlertCircle className="w-3 h-3" /> SPAM ({Math.round(log.result.spam_probability * 100)}%) - {getCodeDescription(log.result.classification_code)}
                              </span>
                            ) : (
                              <span className="text-green-400 flex items-center gap-1 bg-green-400/10 px-1.5 rounded text-xs font-bold whitespace-nowrap">
                                <CheckCircle className="w-3 h-3" /> HAM
                              </span>
                            )}
                            {/* 수정 버튼 */}
                            <button
                              onClick={() => openEditModal(idx, log)}
                              className="p-1 rounded hover:bg-slate-700 transition-colors text-slate-500 hover:text-yellow-400"
                              title="결과 수정"
                              disabled={!downloadFilename}
                            >
                              <Pencil className="w-3 h-3" />
                            </button>
                            {/* RAG 저장 버튼 */}
                            <button
                              onClick={() => openRagWithData(
                                log.message,
                                log.result.is_spam,
                                log.result.classification_code,
                                log.result.reason
                              )}
                              className="p-1 rounded hover:bg-slate-700 transition-colors text-slate-500 hover:text-blue-400"
                              title="RAG DB에 저장"
                            >
                              <Database className="w-3 h-3" />
                            </button>
                          </>
                        ) : (
                          <span className="text-blue-400 text-xs">Processing...</span>
                        )}
                        <span className="text-slate-500 ml-auto text-xs whitespace-nowrap">
                          [{log.timestamp ? log.timestamp.toLocaleTimeString() : new Date().toLocaleTimeString()}]
                        </span>
                      </div>

                      <div className="text-slate-300 break-all text-sm">
                        {formatMessageWithLinks(log.message)}
                      </div>

                      {log.result && (
                        <div className="text-xs text-slate-500 mt-1 pl-2 border-l-2 border-slate-700">
                          <div>{cleanReason}</div>
                          {(isManual || note) && (
                            <div className="flex items-center gap-2 mt-1.5 text-blue-400/80">
                              <User className="w-3 h-3" />
                              {note ? <span>{note}</span> : <span>Manual Decision</span>}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
          </div>
        </div>

      </div>

      {/* RAG Manager Modal */}
      <RagManager
        isOpen={isRagManagerOpen}
        onClose={() => {
          setIsRagManagerOpen(false);
          setRagInitialData(undefined);
        }}
        initialData={ragInitialData}
      />

      {/* 결과 수정 Modal */}
      {editModalOpen && editingLog && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg mx-4 shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <Pencil className="w-5 h-5 text-yellow-400" />
                결과 수정
              </h2>
              <button
                onClick={() => { setEditModalOpen(false); setEditingLog(null); }}
                className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="p-4 space-y-4">
              {/* 메시지 (읽기 전용) */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">메시지</label>
                <div className="p-2 bg-slate-800 rounded border border-slate-700 text-sm text-slate-400 max-h-20 overflow-auto">
                  {editingLog.message}
                </div>
              </div>

              {/* 판정 */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">판정</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => setEditingLog({ ...editingLog, is_spam: true, classification_code: editingLog.classification_code || '1' })}
                    className={`flex-1 py-2 rounded-lg font-medium transition-colors ${editingLog.is_spam
                      ? 'bg-red-500 text-white'
                      : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                      }`}
                  >
                    SPAM
                  </button>
                  <button
                    onClick={() => setEditingLog({ ...editingLog, is_spam: false, classification_code: '' })}
                    className={`flex-1 py-2 rounded-lg font-medium transition-colors ${!editingLog.is_spam
                      ? 'bg-green-500 text-white'
                      : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                      }`}
                  >
                    HAM
                  </button>
                </div>
              </div>

              {/* 분류 코드 (SPAM일 때만) */}
              {editingLog.is_spam && (
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">분류 코드</label>
                  <select
                    value={editingLog.classification_code}
                    onChange={(e) => setEditingLog({ ...editingLog, classification_code: e.target.value })}
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  >
                    <option value="0">0 - 기타 스팸</option>
                    <option value="1">1 - 유해성 스팸</option>
                    <option value="2">2 - 사기/투자 스팸</option>
                    <option value="3">3 - 불법 도박/대출</option>
                  </select>
                </div>
              )}

              {/* 판단 근거 */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">판단 근거</label>
                <textarea
                  value={editingLog.reason}
                  onChange={(e) => setEditingLog({ ...editingLog, reason: e.target.value })}
                  rows={3}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500 resize-none"
                  placeholder="수정된 판단 근거..."
                />
              </div>
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-slate-700">
              <button
                onClick={() => { setEditModalOpen(false); setEditingLog(null); }}
                className="px-4 py-2 rounded-lg bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
              >
                취소
              </button>
              <button
                onClick={saveEdit}
                disabled={editSaving}
                className="px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600 transition-colors flex items-center gap-2 disabled:opacity-50"
              >
                {editSaving ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    저장 중...
                  </>
                ) : (
                  <>
                    <Save className="w-4 h-4" />
                    저장
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default App;
