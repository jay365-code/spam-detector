import { useState, useEffect, useRef } from 'react';
import { CheckCircle, AlertCircle, User, Database, Pencil, X, Save, Loader2, Search, FileText, FolderOpen, Settings } from 'lucide-react';
import { FileUpload } from './components/FileUpload';
import { StatusPanel } from './components/StatusPanel';
import { ChatInterface } from './components/ChatInterface';
import { RagManager } from './components/RagManager';
import { SettingsModal } from './components/SettingsModal';

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

  // Cancellation State
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancellationMessage, setCancellationMessage] = useState('');

  // RAG Manager State
  const [isRagManagerOpen, setIsRagManagerOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
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

  // Constants for Category (Duplicated from RagManager for now)
  const SPAM_CATEGORY_PRESETS = [
    '도박 / 게임', '성인 / 유흥', '유흥업소', '통신 / 휴대폰 스팸', '대리운전',
    '불법 의약품', '금융 / 대출 사기', '구인 / 부업 (불법·어뷰즈)', '나이트클럽',
    '주식 리딩 / 사기', '로또 사기', '피싱 / 스미싱',
  ];

  const HAM_CATEGORY_PRESETS = [
    '정상 광고/마케팅', '배송/택배 알림', '결제/승인 알림', '예약/일정 안내',
    '공공/행정 안내', '개인 메시지', '기타 정상',
  ];

  const CATEGORY_CODE_MAP: Record<string, string> = {
    '도박 / 게임': '3', '성인 / 유흥': '1', '유흥업소': '1', '통신 / 휴대폰 스팸': '0',
    '대리운전': '0', '불법 의약품': '1', '금융 / 대출 사기': '3',
    '구인 / 부업 (불법·어뷰즈)': '0', '나이트클럽': '1', '주식 리딩 / 사기': '2',
    '로또 사기': '2', '피싱 / 스미싱': '2',
  };

  // 결과 수정 모달 State
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingLog, setEditingLog] = useState<{
    index: number;
    excel_row_number?: number; // Add optional property
    message: string;
    is_spam: boolean;
    classification_code: string;
    category: string;
    reason: string;
    spam_probability: number;
  } | null>(null);
  const [editSaving, setEditSaving] = useState(false);

  // 수정 모달 열기
  const openEditModal = (logIndex: number, log: any) => {
    // [Fix] Fallback for older reports without excel_row_number
    // Assuming 1 header row, so index 0 is row 2
    let rowNumber = log.excel_row_number;
    if (rowNumber === undefined) {
      rowNumber = logIndex + 2;
    } else if (rowNumber < 2) {
      // 0-based index fix (Legacy bug)
      rowNumber = rowNumber + 2;
    }

    setEditingLog({
      index: logIndex,
      excel_row_number: rowNumber,
      message: log.message,
      is_spam: log.result.is_spam,
      classification_code: log.result.classification_code || '',
      category: '', // Report usually doesn't have category, default to empty
      reason: log.result.reason || '',
      spam_probability: log.result.spam_probability || 0.95
    });
    setEditModalOpen(true);
  };

  const handleEditCategoryClick = (cat: string) => {
    if (!editingLog) return;
    const newCode = CATEGORY_CODE_MAP[cat] || editingLog.classification_code;
    setEditingLog({
      ...editingLog,
      category: cat,
      classification_code: newCode
    });
  };

  // 수정 저장
  const saveEdit = async () => {
    if (!editingLog || !downloadFilename) return;

    // Validate excel_row_number exists
    let rowNum = editingLog.excel_row_number;
    if (rowNum === undefined || rowNum === null) {
      // Only fallback if really missing. If 0, we fix below.
      alert('Excel 행 번호 정보가 없습니다.');
      return;
    }
    // [Fix] Double-check for 0-based index
    if (rowNum < 2) {
      rowNum = rowNum + 2;
    }

    setEditSaving(true);
    try {
      // 1. 백엔드 API로 엑셀 업데이트
      const response = await fetch('http://localhost:8000/api/excel/update-row', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: downloadFilename,
          excel_row_number: rowNum,  // Use corrected rowNum
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

  // Cancel Processing Handler
  const handleCancelProcessing = async () => {
    if (isCancelling) {
      alert('이미 중지 요청이 진행 중입니다.');
      return;
    }

    const confirmed = confirm(
      '⚠️ 주의: 즉시 중지되지 않습니다\n\n' +
      '현재 처리 중인 배치(최대 20개 메시지)가 완료된 후 중지됩니다.\n' +
      '계속하시겠습니까?'
    );

    if (!confirmed) return;

    setIsCancelling(true);
    setCancellationMessage('중지 요청 중...');

    try {
      await fetch(`http://localhost:8000/cancel/${clientId}`, {
        method: 'POST'
      });
      setCancellationMessage('현재 배치 완료 대기 중...');
    } catch (error) {
      console.error('Cancel failed:', error);
      alert('중지 요청 실패: ' + error);
      setIsCancelling(false);
      setCancellationMessage('');
    }
  };

  // Progress State
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [isProcessing, setIsProcessing] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null); // [New] Start Time
  const [endTime, setEndTime] = useState<number | null>(null); // [New] End Time

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
  const [logFilter, setLogFilter] = useState<'ALL' | 'SPAM' | 'HAM' | 'FP_SENSITIVE'>('ALL');
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
        let data;
        try {
          data = JSON.parse(event.data);
        } catch (e) {
          console.error('Failed to parse WS message:', event.data);
          return;
        }
        console.log('WS Message:', data);

        // Ignore Chat Streaming messages and Process Status for System Log
        if (data.type && (data.type.startsWith('CHAT_') || data.type === 'PROCESS_STATUS')) return;

        // [New] Handle Batch Process Update (Real-time Streaming)
        if (data.type === 'BATCH_PROCESS_UPDATE') {
          // Update Progress Logic (Moved inside to avoid early return issue)
          if (data.current !== undefined && data.total !== undefined) {
            setProgress({ current: data.current, total: data.total });
            if (data.current < data.total) {
              setIsProcessing(true);
            } else {
              // Only set to false if we are sure it's done?
              // Actually, batch update implies ongoing. 
              // Wait for final "Processing complete" message safely, 
              // but if current == total, we might be done.
              if (data.current === data.total) {
                // Don't set isProcessing false here immediately, let the final response handle it 
                // or just leave it true.
              }
            }
          }

          setLogs(prev => {
            const newLogs = [...prev];
            // Ensure array is large enough (sparse array handling)
            if (newLogs.length <= data.index) {
              // Fill gaps if needed, though usually pushed sequentially on upload
              // Here we just assign to the specific index
            }

            // Construct Log Object
            const logItem = {
              excel_row_number: data.index + 2, // [Fix] Store Excel Row Number (Index + Header + 1-based)
              message: data.message,
              result: data.result,
              timestamp: new Date()
            };

            newLogs[data.index] = logItem;
            return newLogs;
          });
          return;
        }

        // Handle Progress/Log with Deduplication
        setLogs(prev => {
          // If this is a result message (has result), look for matching pending message
          if (data.result && data.message) {
            const index = prev.findIndex(l => l && l.message === data.message && !l.result);
            if (index !== -1) {
              // Found pending log -> matching result; Update it
              const newLogs = [...prev];
              newLogs[index] = { ...data, timestamp: newLogs[index]?.timestamp || new Date() };
              return newLogs;
            }
          }

          // Safety check: Avoid adding exact duplicate results if already present
          const exists = prev.some(l =>
            l && l.message === data.message &&
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

        // Handle Cancellation Confirmation
        if (data.type === 'cancellation_confirmed') {
          console.log('Cancellation confirmed:', data.message);
          setIsProcessing(false);
          // 상태를 유지하여 UI에 메시지가 계속 보이게 함
          setIsCancelling(true);
          setCancellationMessage('🚫 중간에 강제 중지 되었습니다.');
          // 로그 출력 제거
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
    setStartedAt(Date.now()); // [New] Set Start Time
    setEndTime(null); // Reset End Time
    setDownloadUrl(null);
    setDownloadFilename(null);
    setHitlRequest(null);
    setActiveReportName(null); // 분석 시작 시 보고서 모드 해제
    setActiveReportFileName(null);
    // Reset cancellation state
    setIsCancelling(false);
    setCancellationMessage('');
  };

  const handleUploadComplete = (filename: string) => {
    setIsProcessing(false);
    setEndTime(Date.now()); // Capture Finish Time
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

  const handleStopChat = async () => {
    try {
      await fetch(`http://localhost:8000/cancel/${clientId}`, {
        method: 'POST'
      });
      console.log('Chat cancellation requested');
    } catch (error) {
      console.error('Chat cancel failed:', error);
    }
  };

  const handleClearChat = () => {
    // Optional: Logic to clear logs or reset other states if needed
    console.log("Chat cleared");
  };

  // [New] Filter & Count Logic
  const allCount = logs.length;
  const spamCount = logs.filter(l => l?.result?.is_spam && l?.result?.semantic_class !== 'Type_B').length;
  const hamCount = logs.filter(l => l?.result && !l.result.is_spam).length;
  const fpSensitiveCount = logs.filter(l => l?.result?.semantic_class === 'Type_B').length;

  const filteredLogs = logs
    .map((log, originalIdx) => ({ ...log, originalIdx }))
    .filter(log => {
      // Apply Filter
      if (logFilter === 'SPAM' && (!log.result || !log.result.is_spam || log.result.semantic_class === 'Type_B')) return false;
      if (logFilter === 'HAM' && (!log.result || log.result.is_spam)) return false;
      if (logFilter === 'FP_SENSITIVE' && log.result?.semantic_class !== 'Type_B') return false;

      // Apply Search
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesMsg = log.message?.toLowerCase().includes(query);
        const matchesReason = log.result?.reason?.toLowerCase().includes(query);
        return matchesMsg || matchesReason;
      }
      return true;
    });

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
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setIsRagManagerOpen(true)}
                className="flex items-center justify-center p-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg transition-colors"
                title="스팸 RAG"
              >
                <Database className="w-4 h-4 text-blue-400" />
              </button>
              <button
                onClick={() => setIsSettingsOpen(true)}
                className="flex items-center justify-center p-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg transition-colors"
                title="Settings"
              >
                <Settings className="w-4 h-4 text-purple-400" />
              </button>
            </div>
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
                  setLogs([]);
                  setIsCancelling(false);
                  setCancellationMessage('');
                }}
              />
            </div>
            {(isProcessing || (downloadUrl && progress.total > 0)) && (
              <div className="flex-1 max-w-sm min-w-[300px]">
                <StatusPanel
                  current={progress.current}
                  total={progress.total}
                  isProcessing={isProcessing}
                  startTime={startedAt} // [New] Pass Start Time
                  endTime={endTime} // [New] Pass End Time
                  downloadUrl={downloadUrl}
                  onDownload={handleExcelSaveAs}
                  isCancelling={isCancelling}
                  cancellationMessage={cancellationMessage}
                  onCancel={handleCancelProcessing}
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
            onStopGeneration={handleStopChat}
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
              {[
                { label: 'ALL', count: allCount, filterKey: 'ALL', activeClass: 'bg-blue-500 text-white shadow-lg', inactiveClass: 'text-slate-400 hover:text-slate-200' },
                { label: 'SPAM', count: spamCount, filterKey: 'SPAM', activeClass: 'bg-red-500 text-white shadow-lg', inactiveClass: 'text-red-400 hover:text-red-200' },
                { label: 'FP SENSITIVE', count: fpSensitiveCount, filterKey: 'FP_SENSITIVE', activeClass: 'bg-orange-500 text-white shadow-lg', inactiveClass: 'text-orange-400 hover:text-orange-200' },
                { label: 'HAM', count: hamCount, filterKey: 'HAM', activeClass: 'bg-green-600 text-white shadow-lg', inactiveClass: 'text-green-400 hover:text-green-200' },
              ].map(({ label, count, filterKey, activeClass, inactiveClass }) => (
                <button
                  key={filterKey}
                  onClick={() => setLogFilter(filterKey as any)}
                  className={`px-3 py-1 rounded-md transition-all text-xs font-bold flex items-center ${logFilter === filterKey ? activeClass : inactiveClass
                    }`}
                >
                  {label}
                  <span className={`ml-1.5 px-1.5 py-0.5 rounded-full text-[10px] ${logFilter === filterKey ? 'bg-white/20' : 'bg-slate-700'}`}>
                    {count}
                  </span>
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

            {/* Search Result Count */}
            <div className="ml-3 text-xs text-slate-400 font-mono whitespace-nowrap">
              {filteredLogs.length} results
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
            {filteredLogs
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
                            {log.result.semantic_class === 'Type_B' ? (
                              <span className="text-orange-400 flex items-center gap-1 bg-orange-400/10 px-1.5 rounded text-xs font-bold whitespace-nowrap">
                                <AlertCircle className="w-3 h-3" /> FP SENSITIVE ({Math.round(log.result.spam_probability * 100)}%) - {getCodeDescription(log.result.classification_code) || '사칭/위장형 스팸'}
                              </span>
                            ) : log.result.is_spam ? (
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
                          {/* Duration Badge */}
                          {log.result?.duration_seconds && (
                            <span className="mr-2 px-1.5 py-0.5 bg-slate-800 text-slate-400 rounded border border-slate-700">
                              {log.result.duration_seconds}s
                            </span>
                          )}
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

      {/* 결과 수정 Modal (Premium Dark Style) */}
      {editModalOpen && editingLog && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-700 rounded-3xl w-full max-w-2xl mx-4 shadow-2xl overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="flex items-center justify-between px-8 py-5 border-b border-slate-800 bg-slate-900">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-indigo-600 rounded-xl flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
                  <Pencil size={20} />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-white">결과 수정</h2>
                  <p className="text-xs text-slate-400 font-medium">리포트 데이터 및 분석 결과 보정</p>
                </div>
              </div>
              <button
                onClick={() => { setEditModalOpen(false); setEditingLog(null); }}
                className="p-2 hover:bg-slate-800 rounded-xl transition-colors"
              >
                <X size={20} className="text-slate-400 hover:text-white" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-8 space-y-6 max-h-[75vh] custom-scrollbar">
              {/* Message (Readonly) */}
              <div>
                <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">메시지 원문</label>
                <div className="p-4 bg-slate-950 border border-slate-800 rounded-2xl text-slate-300 text-sm leading-relaxed max-h-32 overflow-y-auto whitespace-pre-wrap">
                  {editingLog.message}
                </div>
              </div>

              {/* Status Grid */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">판정</label>
                  <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800">
                    <button
                      onClick={() => setEditingLog({ ...editingLog, is_spam: true, classification_code: editingLog.classification_code || '1' })}
                      className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${editingLog.is_spam
                        ? 'bg-rose-500/20 text-rose-400 shadow-sm'
                        : 'text-slate-500 hover:text-slate-300'
                        }`}
                    >
                      SPAM
                    </button>
                    <button
                      onClick={() => setEditingLog({ ...editingLog, is_spam: false, classification_code: '' })}
                      className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${!editingLog.is_spam
                        ? 'bg-emerald-500/20 text-emerald-400 shadow-sm'
                        : 'text-slate-500 hover:text-slate-300'
                        }`}
                    >
                      HAM
                    </button>
                  </div>
                </div>

                {editingLog.is_spam && (
                  <div>
                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">분류 코드</label>
                    <select
                      value={editingLog.classification_code}
                      onChange={(e) => setEditingLog({ ...editingLog, classification_code: e.target.value })}
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
                  {(editingLog.is_spam ? SPAM_CATEGORY_PRESETS : HAM_CATEGORY_PRESETS).map(cat => (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => handleEditCategoryClick(cat)}
                      className={`px-3 py-1.5 text-xs rounded-xl border transition-all ${editingLog.category === cat
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
                  value={editingLog.category}
                  onChange={(e) => setEditingLog({ ...editingLog, category: e.target.value })}
                  placeholder="직접 입력..."
                  className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all placeholder-slate-600"
                />
              </div>

              {/* Reason */}
              <div>
                <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">판단 근거</label>
                <textarea
                  value={editingLog.reason}
                  onChange={(e) => setEditingLog({ ...editingLog, reason: e.target.value })}
                  rows={4}
                  className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-2xl text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all resize-none placeholder-slate-600"
                  placeholder="Intent / Tactics / Action (의도 / 전술 / 행동)"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="flex gap-3 px-8 py-5 border-t border-slate-800 bg-slate-900">
              <button
                onClick={() => { setEditModalOpen(false); setEditingLog(null); }}
                className="flex-1 py-3.5 rounded-2xl bg-slate-800 text-slate-300 font-bold hover:bg-slate-700 transition-all"
              >
                취소
              </button>
              <button
                onClick={saveEdit}
                disabled={editSaving}
                className="flex-[2] py-3.5 rounded-2xl bg-indigo-600 text-white font-bold hover:bg-indigo-500 transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {editSaving ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    저장 중...
                  </>
                ) : (
                  <>
                    <Save className="w-5 h-5" />
                    저장
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      <RagManager
        isOpen={isRagManagerOpen}
        onClose={() => setIsRagManagerOpen(false)}
        initialData={ragInitialData}
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  );
}

export default App;
