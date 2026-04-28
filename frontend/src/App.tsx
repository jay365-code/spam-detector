import { useState, useEffect, useRef, useMemo } from 'react';
import { API_BASE, WS_BASE } from './config';
import { CheckCircle, AlertCircle, User, Database, Server, Pencil, X, Save, Loader2, Search, FileText, FolderOpen, Settings, MessageSquare, Copy, Flag } from 'lucide-react';
import { FileUpload } from './components/FileUpload';
import { StatusPanel } from './components/StatusPanel';
import { ChatInterface } from './components/ChatInterface';
import { RagManager } from './components/RagManager';
import { SettingsModal } from './components/SettingsModal';
import { DatabaseManagerModal } from './components/DatabaseManagerModal';
import SignatureRefinerModal from './components/SignatureRefinerModal';
import { ValidationModal } from './components/ValidationModal';

// 백엔드 constants.py 및 spam_guide_20260326.md 기준 (0-3 코드 체계)
const CLASSIFICATION_MAP: Record<string, string> = {
  "0": "일반 (인터넷, 통신, 대리운전 등)",
  "1": "성인 (유흥업소, 성인용품/약품/컨텐츠 등)",
  "2": "도박 (도박, 주식, 가상자산, 스미싱 및 기타 모든 스팸)",
  "3": "금융 (대출)",
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

// 로그 항목 타입 정의
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type LogEntry = any;

function App() {
  const [clientId] = useState(() => 'client-' + Math.random().toString(36).substr(2, 9));
  const [logs, setLogs] = useState<Record<number, LogEntry>>({});
  const [reportTab, setReportTab] = useState<'MAIN' | 'TRAP' | 'ALL'>('MAIN');
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [downloadFilename, setDownloadFilename] = useState<string | null>(null);
  const [kisaFilename, setKisaFilename] = useState<string>('MAIN');
  const [trapFilename, setTrapFilename] = useState<string>('TRAP');
  const [tokenUsage, setTokenUsage] = useState<Record<string, { in: number; out: number }> | null>(null); // [New] Token Usage Tracking

  // Cancellation State
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancellationMessage, setCancellationMessage] = useState('');
  const [cancelConfirmOpen, setCancelConfirmOpen] = useState(false);

  // RAG Manager State
  const [isRagManagerOpen, setIsRagManagerOpen] = useState(false);
  const [isRefinerModalOpen, setIsRefinerModalOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isDbManagerOpen, setIsDbManagerOpen] = useState(false);
  const [isValidationModalOpen, setIsValidationModalOpen] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(false); // [New] Chat Panel State
  const [chatWidth, setChatWidth] = useState(450); // [New] Resizable Chat Width
  const [isChatDragging, setIsChatDragging] = useState(false); // [New] Chat Resize State
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
    '도박 / 게임': '2', '성인 / 유흥': '1', '유흥업소': '1', '통신 / 휴대폰 스팸': '0',
    '대리운전': '0', '불법 의약품': '1', '금융 / 대출 사기': '3',
    '구인 / 부업 (불법·어뷰즈)': '2', '나이트클럽': '1', '주식 리딩 / 사기': '2',
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
    is_trap?: boolean;
    red_group?: boolean;
    flagged?: boolean;
    malicious_url_extracted?: boolean;
    drop_url?: boolean;
    drop_url_reason?: string | null;
  } | null>(null);
  
  // Wizard State
  const [wizardStep, setWizardStep] = useState<1 | 2>(1);
  const [extractedUrls, setExtractedUrls] = useState<string[]>([]);
  const [extractedSignature, setExtractedSignature] = useState<string>('');
  const [inputUrl, setInputUrl] = useState<string>('');
  const [isExtracting, setIsExtracting] = useState(false);
  const [isUrlExtracting, setIsUrlExtracting] = useState(false);
  const [editSaving, setEditSaving] = useState(false);

  // 수정 모달 열기
  const openEditModal = (logIndex: number, log: LogEntry) => {
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
      spam_probability: log.result.spam_probability || 0.95,
      is_trap: log.is_trap || false,
      // [Fix] 기존 Red Group 상태 복원: 모달 열 때 항상 false로 초기화하던 버그 수정
      red_group: log.result.red_group || false,
      flagged: log.result.flagged || false,
      malicious_url_extracted: log.result.malicious_url_extracted,
      drop_url: log.result.drop_url,
      drop_url_reason: log.result.drop_url_reason
    });
    setWizardStep(1);
    setExtractedUrls([]);
    setExtractedSignature(log.result.ibse_signature || ''); // 기존 시그니처 유지 (저장 시 빈값으로 덮어쓰는 것 방지)
    setInputUrl(log.request?.url || '');
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

  const handleFirstStepSave = () => {
    if (!editingLog) return;
    const originalLog = logs[editingLog.index];
    const wasSpam = originalLog?.result?.is_spam;
    if (!wasSpam && editingLog.is_spam) {
      setWizardStep(2);
    } else {
      saveEdit();
    }
  };

  const handleExtractUrl = async () => {
      setIsUrlExtracting(true);
      try {
          const res = await fetch(`${API_BASE}/api/utils/extract-url`, {
             method: 'POST',
             headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify({ message: editingLog?.message || "" })
          });
          const data = await res.json();
          setExtractedUrls(data.urls || []);
      } catch {
          alert('URL 추출 중 오류 발생');
      } finally {
          setIsUrlExtracting(false);
      }
  };

  const handleExtractSignature = async () => {
      setIsExtracting(true);
      try {
          const res = await fetch(`${API_BASE}/api/ibse/extract`, {
             method: 'POST',
             headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify({ message: editingLog?.message || "" })
          });
          const data = await res.json();
          if (data.signature) {
             setExtractedSignature(data.signature);
          } else {
             alert('시그니처 추출 실패, 대상이 없거나 생성할 수 없습니다.');
          }
      } catch {
          alert('시그니처 추출 중 오류 발생');
      } finally {
          setIsExtracting(false);
      }
  };

  // 수정 저장
  const saveEdit = async () => {
    if (!editingLog) return;

    // 시그니처 바이트 길이 검증 (있을 경우에만)
    if (extractedSignature && !['none', 'unextractable'].includes(extractedSignature.toLowerCase().trim())) {
        const calcByteLen = (str: string) => [...(str || '')].reduce((acc, ch) => acc + (ch.charCodeAt(0) > 127 ? 2 : 1), 0);
        const sigLen = calcByteLen(extractedSignature.trim());
        
        if (!((sigLen >= 9 && sigLen <= 20) || (sigLen >= 39 && sigLen <= 40))) {
            alert(`[저장 실패] 시그니처 길이가 정책에 어긋납니다.\n현재 길이: ${sigLen} byte\n허용 길이: 9~20 byte 또는 39~40 byte\n(공백 제거 후 다시 시도해보세요)`);
            return;
        }
    }

    setEditSaving(true);
    try {
      // UI 상태만 즉각 업데이트 (백엔드는 엑셀 최종 저장 시 JSON 전체 기반으로 재생성)
      setLogs(prev => {
        const newLogs = { ...prev };
        if (newLogs[editingLog.index]) {
          newLogs[editingLog.index] = {
            ...newLogs[editingLog.index],
            request: {
              ...newLogs[editingLog.index].request,
              url: inputUrl
            },
            result: {
              ...newLogs[editingLog.index].result,
              is_spam: editingLog.is_spam,
              classification_code: editingLog.classification_code,
              reason: editingLog.reason,
              red_group: editingLog.red_group || false,
              flagged: editingLog.flagged || false,
              // [Fix] 수동 Red Group 지정 시, AI가 설정한 drop_url 플래그를 해제하여 URL이 엑셀에 표시되도록 함.
              // 사용자가 Red Group을 수동으로 지정한다는 것은 "이 URL은 악성이다"는 명시적 의사 표현이므로
              // AI의 URL 제거 결정을 무시하고 drop_url을 false로 오버라이드 합니다.
              spam_probability: editingLog.spam_probability,
              message_extracted_url: extractedUrls.join(', '),
              ibse_signature: extractedSignature ? extractedSignature.trim() : extractedSignature,
              ibse_len: extractedSignature ? [...(extractedSignature.trim() || '')].reduce((acc, ch) => acc + (ch.charCodeAt(0) > 127 ? 2 : 1), 0) : 0,
              ...(editingLog.malicious_url_extracted !== undefined ? { malicious_url_extracted: editingLog.malicious_url_extracted } : {}),
              ...(editingLog.drop_url !== undefined ? { drop_url: editingLog.red_group ? false : editingLog.drop_url } : {}),
              ...(editingLog.drop_url_reason !== undefined ? { drop_url_reason: editingLog.red_group ? null : editingLog.drop_url_reason } : {})
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

  // Cancel Processing Handler - 커스텀 모달로 교체 (window.confirm은 WebSocket 리렌더 중 강제 닫힘 버그 존재)
  const handleCancelProcessing = () => {
    if (isCancelling) return;
    setCancelConfirmOpen(true); // 커스텀 모달 열기
  };

  const confirmCancel = async () => {
    setCancelConfirmOpen(false);
    setIsCancelling(true);
    setCancellationMessage('중지 요청 중...');

    try {
      await fetch(`${API_BASE}/cancel/${clientId}`, {
        method: 'POST'
      });
      setCancellationMessage('현재 배치 완료 대기 중...');
    } catch (error) {
      console.error('Cancel failed:', error);
      setIsCancelling(false);
      setCancellationMessage('중지 실패 (네트워크 오류)');
    }
  };

  // Progress State
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [isProcessing, setIsProcessing] = useState(false);
  const [isRegeneratingExcel, setIsRegeneratingExcel] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null); // [New] Start Time
  const [endTime, setEndTime] = useState<number | null>(null); // [New] End Time

  // HITL State
  const [hitlRequest, setHitlRequest] = useState<Record<string, unknown> | null>(null);

  const [isConnected, setIsConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);

  // Filter & Search State
  const [logFilter, setLogFilter] = useState<'ALL' | 'SPAM' | 'HAM' | 'RED_GROUP' | 'FP_SENSITIVE' | 'FLAGGED' | 'REVIEW'>('ALL');
  const [reviewCategory, setReviewCategory] = useState<string>('all');
  const [reviewSort, setReviewSort] = useState<'similarity' | 'probability'>('probability');
  const [searchQuery, setSearchQuery] = useState('');
  const preSearchScrollTopRef = useRef<number | null>(null);

  // [New] Filter Scroll Retention
  const filterScrollTopsRef = useRef<Record<string, number>>({});
  const handleFilterChange = (newFilter: 'ALL' | 'SPAM' | 'HAM' | 'RED_GROUP' | 'FP_SENSITIVE' | 'FLAGGED' | 'REVIEW') => {
    if (logContainerRef.current) {
      filterScrollTopsRef.current[logFilter] = logContainerRef.current.scrollTop;
    }
    setLogFilter(newFilter);
  };

  useEffect(() => {
    // Wait for React DOM update cycle before applying scroll
    setTimeout(() => {
      if (logContainerRef.current && filterScrollTopsRef.current[logFilter] !== undefined) {
        logContainerRef.current.scrollTop = filterScrollTopsRef.current[logFilter];
      }
    }, 0);
  }, [logFilter]);

  const handleSearchChange = (val: string) => {
    if (!searchQuery && val) {
      // 처음 검색어를 입력하기 시작할 때 현재 스크롤 위치 저장
      if (logContainerRef.current) {
        preSearchScrollTopRef.current = logContainerRef.current.scrollTop;
      }
    } else if (searchQuery && !val) {
      // 검색어를 완전히 지웠을 때 기존 스크롤 위치 복원
      if (logContainerRef.current && preSearchScrollTopRef.current !== null) {
        const targetScroll = preSearchScrollTopRef.current;
        // React 렌더링 사이클(리스트 복구) 이후에 스크롤을 이동시키기 위해 setTimeout 사용
        setTimeout(() => {
          if (logContainerRef.current) {
            logContainerRef.current.scrollTop = targetScroll;
          }
          preSearchScrollTopRef.current = null;
        }, 0);
      }
    }
    setSearchQuery(val);
  };

  // Header Collapse State (제목/파일 정보 접기)
  const [headerCollapsed, setHeaderCollapsed] = useState(false);
  // Advanced Filter State
  const [filterPanelOpen, setFilterPanelOpen] = useState(false);
  const [advancedFilters, setAdvancedFilters] = useState({
    msgLenMin: '' as string,
    msgLenMax: '' as string,
    classificationCodes: [] as string[],
    hasUrl: 'all' as 'all' | 'yes' | 'no',
    hasSignature: 'all' as 'all' | 'yes' | 'no',
    probMin: '' as string,
    probMax: '' as string,
    cacheType: 'all' as 'all' | 'url_db' | 'url_runtime' | 'sig_db' | 'sig_runtime',
    showClusterOnly: false
  });
  const [clusterGroupsData, setClusterGroupsData] = useState<Array<{cluster_id: number, items: LogEntry[]}>>([]);
  const [isClusterViewMode, setIsClusterViewMode] = useState(false);
  const [isFetchingClusters, setIsFetchingClusters] = useState(false);

  const toggleClusterViewMode = async () => {
    const nextVal = !isClusterViewMode;
    setIsClusterViewMode(nextVal);
    
    const targetFile = activeReportFileName || downloadFilename || 'realtime_report.json';
    if (nextVal && Object.keys(logs).length > 0) {
      setIsFetchingClusters(true);
      try {
        const res = await fetch(`${API_BASE}/api/reports/${encodeURIComponent(targetFile)}/cluster-all`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ logs })
        });
        if (res.ok) {
          const data = await res.json();
          setClusterGroupsData(data?.clusters || []);
        } else {
          setIsClusterViewMode(false);
        }
      } catch(err) {
        console.error("Cluster all fetch Error:", err);
        setIsClusterViewMode(false);
      } finally {
        setIsFetchingClusters(false);
      }
    }
  };

  // CP949 근사 바이트 계산 (비ASCII = 2byte, ASCII = 1byte)
  const calcByteLen = (str: string) =>
    [...(str || '')].reduce((acc, ch) => acc + (ch.charCodeAt(0) > 127 ? 2 : 1), 0);
  const isAdvancedFilterActive = advancedFilters.msgLenMin !== '' || advancedFilters.msgLenMax !== '' ||
    advancedFilters.classificationCodes.length > 0 || advancedFilters.hasUrl !== 'all' ||
    advancedFilters.hasSignature !== 'all' || advancedFilters.probMin !== '' || advancedFilters.probMax !== '' ||
    advancedFilters.cacheType !== 'all' || advancedFilters.showClusterOnly;

  const activeFilterTags = useMemo(() => {
    const tags: { label: string, action: () => void }[] = [];
    const af = advancedFilters;
    if (af.msgLenMin || af.msgLenMax) {
      tags.push({
         label: `길이:${af.msgLenMin || '0'}~${af.msgLenMax || '∞'}B`,
         action: () => setAdvancedFilters(prev => ({ ...prev, msgLenMin: '', msgLenMax: '' }))
      });
    }
    if (af.classificationCodes.length > 0) {
      tags.push({
         label: `코드:${af.classificationCodes.join(',')}`,
         action: () => setAdvancedFilters(prev => ({ ...prev, classificationCodes: [] }))
      });
    }
    if (af.probMin || af.probMax) {
      tags.push({
         label: `확률:${af.probMin || '0'}~${af.probMax || '1'}`,
         action: () => setAdvancedFilters(prev => ({ ...prev, probMin: '', probMax: '' }))
      });
    }
    if (af.hasUrl !== 'all') {
      tags.push({
         label: `URL:${af.hasUrl === 'yes' ? 'O' : 'X'}`,
         action: () => setAdvancedFilters(prev => ({ ...prev, hasUrl: 'all' }))
      });
    }
    if (af.hasSignature !== 'all') {
      tags.push({
         label: `시그니처:${af.hasSignature === 'yes' ? 'O' : 'X'}`,
         action: () => setAdvancedFilters(prev => ({ ...prev, hasSignature: 'all' }))
      });
    }
    if (af.cacheType !== 'all') {
      const cacheMap = {
        'url_db': 'URL DB',
        'url_runtime': 'URL 런타임',
        'sig_db': 'SIG DB',
        'sig_runtime': 'SIG 런타임'
      };
      tags.push({
         label: `캐시:${cacheMap[af.cacheType as keyof typeof cacheMap]}`,
         action: () => setAdvancedFilters(prev => ({ ...prev, cacheType: 'all' }))
      });
    }
    if (af.showClusterOnly) {
      tags.push({
         label: `유사 클러스터 대상만`,
         action: () => setAdvancedFilters(prev => ({ ...prev, showClusterOnly: false }))
      });
    }
    return tags;
  }, [advancedFilters]);

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

        const logsObj = Array.isArray(data.logs) ? data.logs : Object.values(data.logs || {});
        const validLogsRaw = logsObj.filter((l: LogEntry) => l !== null && l !== undefined);
        const logMap: Record<number, LogEntry> = {};
        validLogsRaw.forEach((l: LogEntry, i: number) => {
          logMap[l.excel_row_number ? l.excel_row_number - 2 : i] = {
            ...l,
            timestamp: l.timestamp ? new Date(l.timestamp) : new Date()
          };
        });
        setLogs(logMap);
        setDownloadFilename(data.source_filename);
        if (data.kisa_filename) setKisaFilename(data.kisa_filename);
        if (data.trap_filename) setTrapFilename(data.trap_filename);
        if (data.source_filename) {
          setDownloadUrl(`${API_BASE}/download/${encodeURIComponent(data.source_filename)}`);
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

  // 서버에서 리포트 파일을 직접 Fetch하여 갱신 (정제기 등 백엔드 작업 후 화면 리로드용)
  const reloadReportFromServer = async (filename: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/reports/${encodeURIComponent(filename)}`);
      if (!res.ok) throw new Error("Failed to load report from server");
      const json = await res.json();
      // 백엔드 응답: { success: true, data: { logs: {...}, report_name: ..., ... } }
      const data = json.data;
      
      const logsObj = Array.isArray(data.logs) ? data.logs : Object.values(data.logs || {});
      const validLogsRaw = logsObj.filter((l: LogEntry) => l !== null && l !== undefined);
      const logMap: Record<number, LogEntry> = {};
      validLogsRaw.forEach((l: LogEntry, i: number) => {
        logMap[l.excel_row_number ? l.excel_row_number - 2 : i] = {
          ...l,
          timestamp: l.timestamp ? new Date(l.timestamp) : new Date()
        };
      });
      setLogs(logMap);
      setDownloadFilename(data.source_filename);
      if (data.kisa_filename) setKisaFilename(data.kisa_filename);
      if (data.trap_filename) setTrapFilename(data.trap_filename);
      if (data.source_filename) {
        setDownloadUrl(`${API_BASE}/download/${encodeURIComponent(data.source_filename)}`);
      }
      setActiveReportName(data.report_name);
    } catch (e) {
      console.error("reloadReportFromServer error:", e);
    }
  };

  const handleExcelSaveAs = async () => {
    if (!downloadUrl || !downloadFilename) return;

    try {
      // 항상 엑셀 분석 결과의 원본 파일네이밍(downloadFilename)을 우선 사용합니다.
      const suggestedExcelName = downloadFilename;
      let fileHandle = null;

      // 1. Open Save File Picker FIRST 
      // (This must happen immediately after click to satisfy browser security before network await)
      if ('showSaveFilePicker' in window) {
        // @ts-expect-error - showSaveFilePicker는 표준 미지원 브라우저 API
        fileHandle = await window.showSaveFilePicker({
          suggestedName: suggestedExcelName,
          types: [{
            description: 'Excel File',
            accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] },
          }],
        });
      }

      // 2. UI에 저장된 전체 JSON 상태를 백엔드로 보내 백지에서 완성본 엑셀 생성 (Regenerate)
      setIsRegeneratingExcel(true);
      const response = await fetch(`${API_BASE}/api/excel/regenerate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: suggestedExcelName,
          is_trap: (suggestedExcelName || '').toLowerCase().includes('trap'),
          logs: Object.values(logs).filter(l => l !== null && l !== undefined && typeof l === 'object')
        })
      });
      
      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`서버 응답 오류: ${response.status}\n${errText}`);
      }
      const blob = await response.blob();

      // 3. Write to selected file
      if (fileHandle) {
        const writable = await fileHandle.createWritable();
        await writable.write(blob);
        await writable.close();
      } else {
        // Fallback (Safari, Firefox 등)
        const fallbackName = activeReportFileName
          ? activeReportFileName.replace(/\.json$/i, ".xlsx")
          : downloadFilename;
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = fallbackName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        console.error('Excel Save As failed:', err);
        alert(`엑셀 재생성 및 다운로드 실패: ${(err as Error).message}`);
      }
    } finally {
      setIsRegeneratingExcel(false);
    }
  };

  // Handle Save Report (Force Windows Save As Explorer)
  const handleDownloadReport = async () => {
    if (Object.keys(logs).length === 0) return;

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
        // @ts-expect-error - showSaveFilePicker는 표준 미지원 브라우저 API
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
          kisa_filename: kisaFilename,
          trap_filename: trapFilename,
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
          kisa_filename: kisaFilename,
          trap_filename: trapFilename,
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
  const previousLogCountRef = useRef(0);
  useEffect(() => {
    const currentCount = Object.keys(logs).length;
    if (currentCount > previousLogCountRef.current) {
      if (isAtBottom && logContainerRef.current) {
        logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
      }
    }
    previousLogCountRef.current = currentCount;
  }, [logs, isAtBottom]);

  // WebSocket Connection (Auto-Reconnect)
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    const connect = () => {
      console.log('Attempting WebSocket connection...');
      ws = new WebSocket(`${WS_BASE}/ws/${clientId}`);

      ws.onopen = () => {
        console.log('Connected to WebSocket');
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          console.error('Failed to parse WS message:', event.data);
          return;
        }
        console.log('WS Message:', data);

        // Ignore Chat Streaming messages and Process Status for System Log
        if (data.type && (data.type.startsWith('CHAT_') || data.type === 'PROCESS_STATUS')) return;

          // [New] Handle Batch Process Update (Real-time Streaming)
          if (data.type === 'BATCH_PROCESS_UPDATE') {
            // Update Progress Logic
            if (data.current !== undefined && data.total !== undefined) {
              setProgress({ current: data.current, total: data.total });
              if (data.current < data.total) {
                setIsProcessing(true);
              } else {
                if (data.current === data.total) {
                  // Done matching backend logic
                  setIsProcessing(false); // Make sure to stop spinner when done
                }
              }
            }
            
            // [New] Update token usage state if available
            if (data.token_usage) {
              setTokenUsage(data.token_usage);
            }
  
            // If this is just the initial broadcast, skip adding an empty log row
            if (data.status === 'started') {
                return;
            }
  
            setLogs(prev => {
              const logItem = {
                excel_row_number: data.index + 2, // [Fix] Store Excel Row Number (Index + Header + 1-based)
                message: data.message,
                request: data.request || {},
                result: data.result,
                is_trap: data.is_trap,
                timestamp: new Date()
              };
              
              return {
                ...prev,
                [data.index]: logItem
              };
            });
            return;
          }

        // Handle Progress/Log with Deduplication (Legacy/Direct)
        setLogs(prev => {
          const prevValues = Object.entries(prev);
          
          // If this is a result message (has result), look for matching pending message
          if (data.result && data.message) {
            const matchIndex = prevValues.findIndex(([, l]) => l && l.message === data.message && !l.result);
            if (matchIndex !== -1) {
              const [keyStr, oldLog] = prevValues[matchIndex];
              const logKey = Number(keyStr);
              return {
                ...prev,
                [logKey]: { ...data, timestamp: oldLog?.timestamp || new Date() }
              };
            }
          }

          // Safety check: Avoid adding exact duplicate results if already present
          const exists = prevValues.some(([, l]) =>
            l && l.message === data.message &&
            l.result && data.result &&
            l.result.reason === data.result.reason
          );
          if (exists) return prev;

          // Otherwise append new log at the next available numeric index
          const nextIndex = prevValues.length > 0 ? Math.max(...prevValues.map(([k]) => Number(k))) + 1 : 0;
          return {
            ...prev,
            [nextIndex]: { ...data, timestamp: new Date() }
          };
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

  // --- Prevent Accidental Close or Refresh ---
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (Object.keys(logs).length > 0 || isProcessing) {
        e.preventDefault();
        // Chrome, Edge 등 현대 브라우저에서 사용자에게 기본 경고창을 띄우기 위한 필수 설정
        e.returnValue = ''; 
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [logs, isProcessing]);

  // --- Auto Save & Restore State for Sleep Mode / Refresh (Session Storage) ---
  const saveTimerRef = useRef<number | null>(null);

  // Restore State on Mount
  useEffect(() => {
    try {
      const backup = sessionStorage.getItem('spamDetectorBackupState');
      if (backup) {
        const parsed = JSON.parse(backup);
        if (parsed.logs && parsed.logs.length > 0 && Object.keys(logs).length === 0) {
           const validLogsRaw = parsed.logs.filter((l: LogEntry) => l !== null && l !== undefined);
           const logMap: Record<number, LogEntry> = {};
           validLogsRaw.forEach((l: LogEntry, i: number) => {
             logMap[l.excel_row_number ? l.excel_row_number - 2 : i] = {
               ...l,
               timestamp: l.timestamp ? new Date(l.timestamp) : new Date()
             };
           });
           setLogs(logMap);
           if (parsed.progress) setProgress(parsed.progress);
           if (parsed.startedAt) setStartedAt(parsed.startedAt);
           if (parsed.endTime) setEndTime(parsed.endTime);
           if (parsed.downloadFilename) {
             setDownloadFilename(parsed.downloadFilename);
             setDownloadUrl(`${API_BASE}/download/${encodeURIComponent(parsed.downloadFilename)}`);
           }
           if (parsed.kisaFilename) setKisaFilename(parsed.kisaFilename);
           if (parsed.trapFilename) setTrapFilename(parsed.trapFilename);
           if (parsed.activeReportName) setActiveReportName(parsed.activeReportName);
           if (parsed.activeReportFileName) setActiveReportFileName(parsed.activeReportFileName);
           console.log("Restored state from sleep mode or refresh!");
        }
      }
    } catch (e) {
      console.warn("Failed to parse backup state", e);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-Save State changes with 2s Debounce (Optimized to not freeze UI)
  useEffect(() => {
    if (Object.keys(logs).length === 0) return; // 빈 상태면 저장 안 함

    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
    }

    saveTimerRef.current = window.setTimeout(() => {
      try {
        const logsArray = Object.values(logs); // Save as array for compatibility
        const stateToSave = {
          logs: logsArray,
          progress,
          startedAt,
          endTime,
          downloadFilename,
          kisaFilename,
          trapFilename,
          activeReportName,
          activeReportFileName
        };
        sessionStorage.setItem('spamDetectorBackupState', JSON.stringify(stateToSave));
      } catch (e) {
         console.warn("Session Storage capacity full or error", e);
      }
    }, 2000);

    return () => {
      if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    };
  }, [logs, progress, isProcessing, startedAt, endTime, downloadFilename, kisaFilename, trapFilename, activeReportName, activeReportFileName]);


  // Chat Resizing Logic
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isChatDragging) return;
      const newWidth = window.innerWidth - e.clientX;
      setChatWidth(Math.max(300, Math.min(newWidth, window.innerWidth - 100)));
    };

    const handleMouseUp = () => {
      setIsChatDragging(false);
    };

    if (isChatDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
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
  }, [isChatDragging]);

  const handleChatResizeMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsChatDragging(true);
  };

  const handleUploadStart = () => {
    setLogs({});
    setProgress({ current: 0, total: 0 });
    setIsProcessing(true);
    setStartedAt(Date.now()); // [New] Set Start Time
    setEndTime(null); // Reset End Time
    setDownloadUrl(null);
    setDownloadFilename(null);
    setKisaFilename('MAIN');
    setTrapFilename('TRAP');
    setHitlRequest(null);
    setTokenUsage(null); // Reset token usage
    setActiveReportName(null); // 분석 시작 시 보고서 모드 해제
    setActiveReportFileName(null);
    // Reset cancellation state
    setIsCancelling(false);
    setCancellationMessage('');
    // 새로운 시작 시 기존 백업 정리
    sessionStorage.removeItem('spamDetectorBackupState');
  };

  const handleUploadComplete = (filename: string, kisaName?: string, trapName?: string) => {
    setIsProcessing(false);
    setEndTime(Date.now()); // Capture Finish Time
    setDownloadFilename(filename);
    if (kisaName) setKisaFilename(kisaName);
    if (trapName) setTrapFilename(trapName);
    setDownloadUrl(`${API_BASE}/download/${encodeURIComponent(filename)}`);
    // 새 분석 완료 시 보고서 모드 해제 (실시간 결과에는 "Loaded:" 배지 미표시)
    setActiveReportName(null);
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
      await fetch(`${API_BASE}/cancel/${clientId}`, {
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

  // [New] Toggle Flag Handler
  const toggleFlag = (index: number) => {
    setLogs(prev => {
      const newLogs = { ...prev };
      if (newLogs[index] && newLogs[index].result) {
        newLogs[index] = {
          ...newLogs[index],
          result: {
            ...newLogs[index].result,
            flagged: !newLogs[index].result.flagged
          }
        };
      }
      return newLogs;
    });
  };

  // [New] Review Category Classification Function
  const getReviewCategory = (log: LogEntry): string | null => {
    const r = log?.result;
    if (!r) return null;
    const reason = r.reason || '';
    const ur = r.url_result || {};

    // ===== 필수 검토 =====
    // HAM Override: reason에 Override 키워드 포함 또는 HAM인데 스팸코드(1,2,3) 잔존
    if (!r.is_spam && (
      reason.includes('Override') || reason.includes('오탐 방어') ||
      ['1','2','3'].includes(String(r.classification_code))
    ))
      return '🔴 필수: HAM Override';
    if (r.is_spam && ur.is_confirmed_safe === true)
      return '🔴 필수: SPAM+방패막이';
    // SPAM Override: Content HAM + URL SPAM → 최종 SPAM (Red Group 아님)
    if (r.is_spam && r.is_pure_content_ham === true && ur.is_spam === true && !r.red_group)
      return '🔴 필수: SPAM Override';

    // ===== 분류코드 기반 카테고리 =====
    const code = String(r.classification_code || '');
    const codeMap: Record<string, string> = {
      '1': '🔞 성인 (코드1)',
      '2': '🎰 도박 (코드2)',
      '3': '💰 대출/금융 (코드3)',
      '0': '📦 일반 (코드0)',
    };
    if (codeMap[code]) return codeMap[code];
    return null;
  };

  // [New] Filter & Count Logic
  // Filter out completely undefined/null items from sparse arrays safely
  const validLogs = Object.keys(logs).map(key => {
    const originalIdx = Number(key);
    return { log: logs[originalIdx], originalIdx };
  }).filter(item => item.log != null);


  // [UI Fix] If the user wants to filter by TRAP/MAIN, we do it inline here:
  const displayLogs = validLogs.filter(item => {
    if (reportTab === 'ALL') return true;
    if (reportTab === 'TRAP') return item.log.is_trap;
    return !item.log.is_trap; // Default to 'MAIN'
  });
  
  console.log("DEBUG: All sparse logs size:", Object.keys(logs).length);
  console.log("DEBUG: Disp logs:", displayLogs.length);
  
  const allCount = displayLogs.length;
  const spamCount = displayLogs.filter(({ log }) => log?.result?.is_spam).length;
  const hamCount = displayLogs.filter(({ log }) => log?.result && !log.result.is_spam).length;
  const redGroupCount = displayLogs.filter(({ log }) => log?.result?.red_group).length;
  const flaggedCount = displayLogs.filter(({ log }) => log?.result?.flagged).length;
  const reviewCount = displayLogs.filter(({ log }) => getReviewCategory(log) !== null).length;

  let filteredLogs = displayLogs
    .filter(({ log }) => {
      // Apply Filter
      if (logFilter === 'SPAM' && (!log.result || !log.result.is_spam)) return false;
      if (logFilter === 'HAM' && (!log.result || log.result.is_spam)) return false;
      if (logFilter === 'RED_GROUP' && (!log.result || !log.result.red_group)) return false;
      if (logFilter === 'FLAGGED' && (!log.result || !log.result.flagged)) return false;
      if (logFilter === 'REVIEW') {
        const cat = getReviewCategory(log);
        if (!cat) return false;
        if (reviewCategory !== 'all' && cat !== reviewCategory) return false;
      }

      // Apply Advanced Filters
      const af = advancedFilters;
      const msgByteLen = calcByteLen(log.message || '');
      if (af.msgLenMin !== '' && msgByteLen < Number(af.msgLenMin)) return false;
      if (af.msgLenMax !== '' && msgByteLen > Number(af.msgLenMax)) return false;
      if (af.classificationCodes.length > 0) {
        const code = String(log.result?.classification_code ?? '');
        if (!af.classificationCodes.includes(code)) return false;
      }
      if (af.hasUrl !== 'all') {
        const hasUrl = !!(log.request?.url && String(log.request.url).trim());
        if (af.hasUrl === 'yes' && !hasUrl) return false;
        if (af.hasUrl === 'no' && hasUrl) return false;
      }
      if (af.hasSignature !== 'all') {
        const hasSig = !!(log.result?.ibse_signature && String(log.result.ibse_signature).trim() &&
          !['none', 'unextractable'].includes(String(log.result.ibse_signature).toLowerCase()));
        if (af.hasSignature === 'yes' && !hasSig) return false;
        if (af.hasSignature === 'no' && hasSig) return false;
      }
      if (af.probMin !== '') {
        const prob = log.result?.spam_probability ?? 0;
        if (prob < Number(af.probMin)) return false;
      }
      if (af.probMax !== '') {
        const prob = log.result?.spam_probability ?? 0;
        if (prob > Number(af.probMax)) return false;
      }

      if (af.cacheType !== 'all') {
        const reason = String(log.result?.reason || '');
        if (af.cacheType === 'url_db' && !reason.includes('[URL DB Cache]')) return false;
        if (af.cacheType === 'url_runtime' && !reason.includes('[URL Runtime Cache]')) return false;
        if (af.cacheType === 'sig_db' && !reason.includes('[SIG DB Cache]')) return false;
        if (af.cacheType === 'sig_runtime' && !reason.includes('[SIG Runtime Cache]')) return false;
      }

      // Apply Search
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        
        let headerText = '';
        if (log.result) {
          if (log.result.is_spam) {
            headerText = `spam ${getCodeDescription(log.result.classification_code)?.toLowerCase() || ''}`;
          } else {
            headerText = 'ham';
          }
        }

        const matchesMsg = log.message?.toLowerCase().includes(query);
        const matchesReason = log.result?.reason?.toLowerCase().includes(query);
        const matchesHeader = headerText.includes(query);
        
        return matchesMsg || matchesReason || matchesHeader;
      }
      return true;
    })
    .map(({ log, originalIdx }) => ({ ...log, originalIdx, cluster_id: undefined as number | undefined }));

  // [Review Mode] 정렬 적용 (REVIEW 필터 활성 시에만)
  if (logFilter === 'REVIEW') {
    if (reviewSort === 'probability') {
      // 확률 0.5 근처(경계선)를 먼저 → 확실한 건은 뒤로
      filteredLogs.sort((a, b) => {
        const pa = a.result?.spam_probability ?? 0;
        const pb = b.result?.spam_probability ?? 0;
        return Math.abs(pa - 0.5) - Math.abs(pb - 0.5);
      });
    } else {
      // 유사 메시지 순: 한글+영문만 추출 후 사전순 (동일 패턴 연속 배치)
      filteredLogs.sort((a, b) => {
        const ma = (a.message || '').replace(/[^\uAC00-\uD7A3a-zA-Z]/g, '').slice(0, 30);
        const mb = (b.message || '').replace(/[^\uAC00-\uD7A3a-zA-Z]/g, '').slice(0, 30);
        return ma.localeCompare(mb);
      });
    }
  }

  // 클러스터별 데이터 갯수 확인을 위해 스코프 상단에 선언
  const clusterSizeMap = new Map<number, number>();
  const clusterSpamMap = new Map<number, number>();

  // [New] 클러스터 뷰 모드 활성화 시 정렬 덮어쓰기 & 필터링 (가리기)
  if (isClusterViewMode && clusterGroupsData.length > 0) {
     const clusterMap = new Map<string, number>();
     clusterGroupsData.forEach(c => {
         c.items.forEach((it: LogEntry) => {
             if (it?.log_id !== undefined && it?.log_id !== null) {
                 clusterMap.set(String(it.log_id), c.cluster_id);
             }
         })
     });

     // 1개짜리 나홀로 스팸은 가리기
     filteredLogs = filteredLogs.filter(entry => clusterMap.has(String(entry.originalIdx)));
     
     // 렌더링을 위해 객체에 cluster_id 먼저 꽂아넣기
     filteredLogs.forEach(entry => {
        entry.cluster_id = clusterMap.get(String(entry.originalIdx));
     });

     // 클러스터별 메시지 및 스팸 개수 계산
     filteredLogs.forEach(entry => {
        const cId = entry.cluster_id!;
        clusterSizeMap.set(cId, (clusterSizeMap.get(cId) || 0) + 1);
        if (entry.result?.is_spam) {
            clusterSpamMap.set(cId, (clusterSpamMap.get(cId) || 0) + 1);
        }
     });

     // 정렬 (1: 스팸 개수 내림차순, 2: 전체 크기 내림차순, 3: cluster_id 오름차순, 4: key 번호 순)
     filteredLogs.sort((a, b) => {
        const ca = a.cluster_id!;
        const cb = b.cluster_id!;
        if (ca !== cb) {
           const spamA = clusterSpamMap.get(ca) || 0;
           const spamB = clusterSpamMap.get(cb) || 0;
           if (spamA !== spamB) return spamB - spamA; // 스팸 개수 최다 순 (내림차순)
           
           const sizeA = clusterSizeMap.get(ca) || 0;
           const sizeB = clusterSizeMap.get(cb) || 0;
           if (sizeA !== sizeB) return sizeB - sizeA; // 그다음 전체 크기 (내림차순)
           
           return ca - cb;
        }
        return a.originalIdx - b.originalIdx;
     });
  }

  return (
    <div className="flex flex-row h-screen w-full bg-slate-900 text-white overflow-hidden">
      {/* Dynamic Main Content Area */}
      <div className="flex-1 flex flex-col h-full relative min-w-0 overflow-hidden transition-all duration-300">
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
                onClick={() => setIsChatOpen(!isChatOpen)}
                className={`flex items-center justify-center p-2 rounded-lg transition-colors border ${isChatOpen ? 'bg-indigo-600 border-indigo-500 text-white shadow-lg shadow-indigo-500/20' : 'bg-slate-800 hover:bg-slate-700 border-slate-600 text-slate-400'}`}
                title="AI 스팸 검증 챗봇"
              >
                <MessageSquare className="w-4 h-4" />
              </button>
              <button
                onClick={() => setIsRagManagerOpen(true)}
                className="flex items-center justify-center p-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg transition-colors text-blue-400"
                title="스팸 RAG"
              >
                <Database className="w-4 h-4" />
              </button>
              <button
                onClick={() => setIsDbManagerOpen(true)}
                className="flex items-center justify-center p-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg transition-colors text-emerald-400"
                title="데이터베이스 관리"
              >
                <Server className="w-4 h-4" />
              </button>
              <button
                onClick={() => setIsSettingsOpen(true)}
                className="flex items-center justify-center p-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg transition-colors"
                title="Settings"
              >
                <Settings className="w-4 h-4 text-purple-400" />
              </button>
              <button
                onClick={() => setIsValidationModalOpen(true)}
                className="flex items-center justify-center p-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg transition-colors text-amber-400 ml-1"
                title="작업 퀄리티 검증"
              >
                <CheckCircle className="w-4 h-4" />
              </button>

              {/* 구분선 */}
              <div className="w-px h-6 bg-slate-600 mx-1" />

              {/* Report Actions (하단에서 이동) */}
              {downloadUrl && activeReportName && (
                <button
                  onClick={handleExcelSaveAs}
                  className="flex items-center justify-center p-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg transition-colors text-green-400"
                  title="엑셀 결과 저장 (Save As)"
                >
                  <ExcelIcon className="w-4 h-4" />
                </button>
              )}
              {(downloadFilename || activeReportFileName) && (
                <button
                  onClick={() => setIsRefinerModalOpen(true)}
                  className="flex items-center justify-center p-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg transition-colors text-indigo-400"
                  title="시그니처 자동 정제 (LLM)"
                >
                  ✨
                </button>
              )}
              <button
                onClick={handleDownloadReport}
                disabled={Object.keys(logs).length === 0}
                className="flex items-center justify-center p-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg transition-colors text-slate-400 disabled:opacity-50"
                title="리포트 저장 (JSON)"
              >
                <Save className="w-4 h-4" />
              </button>
              <button
                onClick={() => reportInputRef.current?.click()}
                className="flex items-center justify-center p-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg transition-colors text-purple-400"
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

              {/* Client Status */}
              <div
                className={`w-2.5 h-2.5 rounded-full ml-1 ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}
                title={isConnected ? 'Connected' : 'Offline'}
              />
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
                  setLogs({});
                  setIsCancelling(false);
                  setCancellationMessage('');
                }}
              />
            </div>
            {(isProcessing || downloadUrl) && (
              <div className="flex-1 max-w-sm min-w-[300px]">
                <StatusPanel
                  current={progress.current}
                  total={progress.total}
                  isProcessing={isProcessing}
                  startTime={startedAt} // [New] Pass Start Time
                  endTime={endTime} // [New] Pass End Time
                  tokenUsage={tokenUsage || undefined} // [New] Pass Token Usage
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

        {/* BOTTOM PANEL: Log Viewer (Now Main Body) */}
        <div
          className="flex-1 min-h-0 bg-slate-900/40 backdrop-blur-md overflow-hidden flex flex-col border-t border-slate-800 shadow-[0_-10px_30px_-15px_rgba(0,0,0,0.5)] z-20 mt-2"
        >
          {/* Header */}
          <div className="px-6 bg-slate-900 border-b border-slate-800/80 text-xs font-mono select-none">
            {/* Row 1: 제목 + 파일 정보 (접기 가능) */}
            {!headerCollapsed && (
              <div className="flex items-center gap-4 py-2 border-b border-slate-800/50">
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-blue-400" />
                  <span className="text-sm font-bold text-slate-200">Spam Detection Report</span>
                  {activeReportName && (
                    <span className="px-2 py-0.5 bg-blue-500/20 text-blue-300 rounded text-[10px]">
                      Loaded: {activeReportName}
                    </span>
                  )}
                </div>

                {/* Main/TRAP Tabs or Single File Name */}
                {trapFilename !== 'TRAP' ? (
                  <div className="flex items-center bg-slate-900 p-1 rounded-lg ml-4 border border-slate-700 max-w-[400px]">
                    <button
                      onClick={() => setReportTab('MAIN')}
                      className={`px-3 py-1 rounded text-xs font-bold transition-colors truncate max-w-[180px] ${reportTab === 'MAIN' ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-slate-300'}`}
                      title={kisaFilename}
                    >
                      {kisaFilename}
                    </button>
                    <button
                      onClick={() => setReportTab('TRAP')}
                      className={`px-3 py-1 rounded text-xs font-bold transition-colors truncate max-w-[180px] ${reportTab === 'TRAP' ? 'bg-slate-700 text-purple-400 shadow' : 'text-slate-400 hover:text-purple-300'}`}
                      title={trapFilename}
                    >
                      {trapFilename}
                    </button>
                  </div>
                ) : (
                  (kisaFilename !== 'MAIN' || validLogs.length > 0) && (
                    <div className="flex items-center bg-slate-900 p-1 rounded-lg ml-4 border border-slate-700 max-w-[400px]">
                      <button
                        className="px-3 py-1 rounded text-xs font-bold transition-colors truncate max-w-[180px] bg-slate-700 text-white shadow cursor-default"
                        title={kisaFilename !== 'MAIN' ? kisaFilename : '분석 데이터'}
                      >
                        {kisaFilename !== 'MAIN' ? kisaFilename : '분석 데이터'}
                      </button>
                    </div>
                  )
                )}

                {/* 접기 버튼 (오른쪽 끝) */}
                <button
                  onClick={() => setHeaderCollapsed(true)}
                  className="ml-auto p-1 rounded hover:bg-slate-700 text-slate-500 hover:text-slate-300 transition-colors"
                  title="헤더 접기"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="18 15 12 9 6 15"/></svg>
                </button>
              </div>
            )}

            {/* Row 2: 필터 + 검색 (항상 표시) */}
            <div className="flex items-center gap-4 py-2">
              {/* 펼치기 버튼 (접힌 상태에서만) */}
              {headerCollapsed && (
                <button
                  onClick={() => setHeaderCollapsed(false)}
                  className="p-1 rounded hover:bg-slate-700 text-slate-500 hover:text-slate-300 transition-colors"
                  title="헤더 펼치기"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                </button>
              )}

            {/* Filter Buttons */}
            <div className="flex items-center bg-slate-900/50 rounded-lg p-1 border border-slate-700">
              {[
                { label: 'ALL', count: allCount, filterKey: 'ALL', activeClass: 'bg-blue-500 text-white shadow-lg', inactiveClass: 'text-slate-400 hover:text-slate-200' },
                { label: 'SPAM', count: spamCount, filterKey: 'SPAM', activeClass: 'bg-red-500 text-white shadow-lg', inactiveClass: 'text-red-400 hover:text-red-200' },
                { label: 'HAM', count: hamCount, filterKey: 'HAM', activeClass: 'bg-green-600 text-white shadow-lg', inactiveClass: 'text-green-400 hover:text-green-200' },
                { label: 'RED GROUP', count: redGroupCount, filterKey: 'RED_GROUP', activeClass: 'bg-pink-500 text-white shadow-lg', inactiveClass: 'text-pink-400 hover:text-pink-200' },
                { label: '검토 필요', count: flaggedCount, filterKey: 'FLAGGED', activeClass: 'bg-yellow-500 text-white shadow-[0_0_12px_rgba(234,179,8,0.6)] ring-1 ring-yellow-400', inactiveClass: 'text-yellow-400 hover:text-yellow-100 bg-yellow-400/10 hover:bg-yellow-400/20 border border-yellow-500/30' },
                { label: '🔍 검토', count: reviewCount, filterKey: 'REVIEW', activeClass: 'bg-purple-500 text-white shadow-[0_0_12px_rgba(168,85,247,0.6)] ring-1 ring-purple-400', inactiveClass: 'text-purple-400 hover:text-purple-100 bg-purple-400/10 hover:bg-purple-400/20 border border-purple-500/30' },
              ].map(({ label, count, filterKey, activeClass, inactiveClass }) => (
                <button
                  key={filterKey}
                  onClick={() => handleFilterChange(logFilter === filterKey ? 'ALL' : filterKey as typeof logFilter)}
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

            {/* Review Category Dropdown + Sort Toggle */}
            {logFilter === 'REVIEW' && (
              <div className="flex items-center gap-2 ml-2">
                <select
                  value={reviewCategory}
                  onChange={e => setReviewCategory(e.target.value)}
                  className="bg-slate-800 border border-purple-500/50 text-purple-200 text-xs rounded-lg px-2 py-1.5 focus:outline-none focus:border-purple-400"
                >
                  <option value="all">전체 검토 대상</option>
                  <option value="🔴 필수: HAM Override">🔴 HAM Override</option>
                  <option value="🔴 필수: SPAM Override">🔴 SPAM Override</option>
                  <option value="🔴 필수: SPAM+방패막이">🔴 SPAM+방패막이</option>
                  <option value="🔞 성인 (코드1)">🔞 성인 (코드1)</option>
                  <option value="🎰 도박 (코드2)">🎰 도박 (코드2)</option>
                  <option value="💰 대출/금융 (코드3)">💰 대출/금융 (코드3)</option>
                  <option value="📦 일반 (코드0)">📦 일반 (코드0)</option>
                </select>
                <div className="flex bg-slate-800 rounded-lg border border-purple-500/30 overflow-hidden">
                  <button
                    onClick={() => setReviewSort('probability')}
                    className={`px-2.5 py-1 text-[10px] font-bold transition-all ${
                      reviewSort === 'probability'
                        ? 'bg-purple-600 text-white'
                        : 'text-purple-400 hover:text-purple-200'
                    }`}
                  >
                    확률순
                  </button>
                  <button
                    onClick={() => setReviewSort('similarity')}
                    className={`px-2.5 py-1 text-[10px] font-bold transition-all ${
                      reviewSort === 'similarity'
                        ? 'bg-purple-600 text-white'
                        : 'text-purple-400 hover:text-purple-200'
                    }`}
                  >
                    유사메시지
                  </button>
                </div>
              </div>
            )}

            {/* Cluster View Toggle */}
            <div className="flex items-center ml-auto bg-indigo-900/20 rounded-lg p-1 border border-indigo-700/50 mr-2">
               <button 
                  onClick={toggleClusterViewMode}
                  className={`flex items-center gap-2 px-3 py-1 rounded text-xs font-bold transition-all ${isClusterViewMode ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20' : 'text-indigo-400 hover:text-indigo-300 hover:bg-slate-800'}`}
               >
                  🗂️ 유사 메시지 묶어보기
                  {isFetchingClusters && <Loader2 className="w-3 h-3 animate-spin"/>}
               </button>
            </div>

            {/* Search Input */}
            <div className={`relative flex-1 max-w-md ml-4 transition-all duration-300 rounded-lg ${searchQuery ? 'ring-1 ring-amber-500 shadow-[0_0_15px_rgba(245,158,11,0.2)] bg-amber-900/10' : ''}`}>
              <Search className={`absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 transition-colors ${searchQuery ? 'text-amber-400' : 'text-slate-500'}`} />
              <input
                type="text"
                placeholder="결과 내 검색..."
                value={searchQuery}
                onChange={(e) => handleSearchChange(e.target.value)}
                className={`w-full bg-slate-900 border rounded-lg pl-8 pr-8 py-1.5 focus:outline-none transition-colors ${
                  searchQuery 
                    ? 'border-amber-500 text-amber-300 placeholder:text-amber-700/50 focus:border-amber-400' 
                    : 'border-slate-700 text-slate-200 focus:border-blue-500'
                }`}
              />
              {searchQuery && (
                <button
                  onClick={() => handleSearchChange('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 bg-amber-500/10 hover:bg-amber-500/30 rounded group transition-colors border border-amber-500/30"
                  title="검색어 초기화"
                >
                  <X className="w-3.5 h-3.5 text-amber-400 group-hover:text-amber-300" />
                </button>
              )}
            </div>

            {/* Go To Item Input */}
            <div className="relative flex items-center max-w-[100px] ml-4 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 transition-colors focus-within:border-blue-500">
              <span className="text-[10px] text-slate-500 font-bold whitespace-nowrap mr-1.5 mt-0.5">No.</span>
              <input
                type="number"
                min="1"
                placeholder="이동명령"
                className="w-full bg-transparent text-xs text-slate-200 outline-none placeholder:text-slate-600 font-mono"
                title="Enter 키를 누르면 해당 번호의 항목으로 스크롤 이동합니다."
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const val = e.currentTarget.value;
                    const num = parseInt(val, 10);
                    if (!isNaN(num) && num > 0) {
                      const el = document.getElementById(`log-item-${num}`);
                      if (el && logContainerRef.current) {
                        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        // 약간의 강조 이펙트 적용
                        el.classList.add('bg-blue-500/30');
                        el.classList.add('border-blue-500/50');
                        setTimeout(() => {
                          if (el) {
                            el.classList.remove('bg-blue-500/30');
                            el.classList.remove('border-blue-500/50');
                          }
                        }, 1500);
                        e.currentTarget.blur();
                      } else {
                        // 찾지 못한 경우 입력칸을 붉게 깜빡임
                        const inputWrap = e.currentTarget.parentElement;
                        if (inputWrap) {
                          inputWrap.classList.add('border-red-500');
                          inputWrap.classList.add('animate-pulse');
                          setTimeout(() => {
                            inputWrap.classList.remove('border-red-500');
                            inputWrap.classList.remove('animate-pulse');
                          }, 1000);
                        }
                      }
                    }
                  }
                }}
              />
            </div>

            {/* Search Result Count */}
            <div className="ml-3 px-2.5 py-1 bg-slate-800 rounded-md text-xs text-slate-300 font-bold whitespace-nowrap border border-slate-700/80 shadow-sm">
              <span className="text-blue-400">{filteredLogs.length}</span> <span className="text-slate-500 font-normal">/ {displayLogs.length} 건</span>
            </div>

            {/* Advanced Filter Toggle Button */}
            <button
              onClick={() => setFilterPanelOpen(v => !v)}
              className={`relative ml-2 p-1.5 rounded-lg transition-colors ${filterPanelOpen ? 'bg-blue-600 text-white' : 'hover:bg-slate-700 text-slate-400 hover:text-slate-200'}`}
              title="고급 필터"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
              </svg>
              {isAdvancedFilterActive && (
                <span className="absolute top-0.5 right-0.5 w-1.5 h-1.5 bg-blue-400 rounded-full" />
              )}
            </button>

            {/* Active Filter Tags */}
            {isAdvancedFilterActive && (
              <div className="flex gap-1 items-center ml-2 mr-1">
                {activeFilterTags.map(tag => (
                  <span key={tag.label} className="bg-slate-800/80 text-blue-300 border border-slate-700/80 pl-2 pr-1 py-0.5 rounded-md text-[10px] font-bold flex items-center gap-1 whitespace-nowrap shadow-sm">
                    {tag.label}
                    <button 
                      onClick={tag.action} 
                      className="p-0.5 ml-0.5 hover:bg-slate-600 rounded-full transition-colors text-slate-400 hover:text-blue-200"
                      title="필터 해제"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}


            </div> {/* End Row 2 */}
          </div> {/* End Header */}

          {/* Advanced Filter Panel */}
          {filterPanelOpen && (
            <div className="border-t border-slate-700 bg-slate-900/80 px-6 py-4 flex flex-col gap-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-bold text-slate-300 uppercase tracking-widest">고급 필터</span>
                {isAdvancedFilterActive && (
                  <button
                    onClick={() => setAdvancedFilters({ msgLenMin: '', msgLenMax: '', classificationCodes: [], hasUrl: 'all', hasSignature: 'all', probMin: '', probMax: '', cacheType: 'all', showClusterOnly: false })}
                    className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                  >
                    초기화
                  </button>
                )}
              </div>
              <div className="grid grid-cols-2 gap-x-8 gap-y-4 lg:grid-cols-3">

                {/* 메시지 길이 */}
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">메시지 길이 (byte)</label>
                  <div className="flex items-center gap-2">
                    <input type="number" min="0" placeholder="최소"
                      value={advancedFilters.msgLenMin}
                      onChange={e => setAdvancedFilters(f => ({ ...f, msgLenMin: e.target.value }))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
                    />
                    <span className="text-slate-500 text-xs">~</span>
                    <input type="number" min="0" placeholder="최대"
                      value={advancedFilters.msgLenMax}
                      onChange={e => setAdvancedFilters(f => ({ ...f, msgLenMax: e.target.value }))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                {/* 분류 코드 */}
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">분류 코드</label>
                  <div className="flex gap-2 flex-wrap">
                    {['0','1','2','3'].map(code => (
                      <button key={code}
                        onClick={() => setAdvancedFilters(f => ({
                          ...f,
                          classificationCodes: f.classificationCodes.includes(code)
                            ? f.classificationCodes.filter(c => c !== code)
                            : [...f.classificationCodes, code]
                        }))}
                        className={`px-3 py-1 rounded-lg text-xs font-bold border transition-all ${
                          advancedFilters.classificationCodes.includes(code)
                            ? 'bg-blue-600 border-blue-500 text-white'
                            : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'
                        }`}
                      >
                        {code}
                      </button>
                    ))}
                  </div>
                </div>

                {/* 스팸 확률 - 듀얼 레인지 슬라이더 */}
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">
                    스팸 확률
                    <span className="text-slate-600 ml-2 text-[10px]">← → 10% | ⌘← → 1%</span>
                  </label>
                  {(() => {
                    const pMin = advancedFilters.probMin === '' ? 0 : Number(advancedFilters.probMin);
                    const pMax = advancedFilters.probMax === '' ? 1 : Number(advancedFilters.probMax);
                    const isActive = advancedFilters.probMin !== '' || advancedFilters.probMax !== '';
                    const leftPct = pMin * 100;
                    const rightPct = pMax * 100;

                    const handleKey = (e: React.KeyboardEvent, which: 'min' | 'max') => {
                      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
                      e.preventDefault();
                      const step = e.metaKey || e.ctrlKey ? 0.01 : 0.1;
                      const dir = e.key === 'ArrowRight' ? 1 : -1;
                      if (which === 'min') {
                        const next = Math.round(Math.max(0, Math.min(pMax - 0.01, pMin + dir * step)) * 100) / 100;
                        setAdvancedFilters(f => ({ ...f, probMin: String(next) }));
                      } else {
                        const next = Math.round(Math.max(pMin + 0.01, Math.min(1, pMax + dir * step)) * 100) / 100;
                        setAdvancedFilters(f => ({ ...f, probMax: String(next) }));
                      }
                    };

                    return (
                      <div className="flex flex-col gap-2">
                        <div className="relative h-6 flex items-center select-none" id="prob-slider-track">
                          <div className="absolute inset-x-0 h-1.5 bg-slate-700 rounded-full" />
                          {/* 활성 범위 막대 — 드래그로 min/max 동시 이동 */}
                          <div
                            className="absolute h-3 rounded-full cursor-grab active:cursor-grabbing z-[5]"
                            style={{
                              left: `${leftPct}%`,
                              right: `${100 - rightPct}%`,
                              background: isActive ? 'linear-gradient(90deg, #3b82f6, #8b5cf6)' : '#475569'
                            }}
                            onMouseDown={e => {
                              e.preventDefault();
                              const track = document.getElementById('prob-slider-track');
                              if (!track) return;
                              const gap = pMax - pMin;
                              const startX = e.clientX;
                              const trackRect = track.getBoundingClientRect();
                              const trackW = trackRect.width;
                              const startMin = pMin;

                              const onMove = (ev: MouseEvent) => {
                                const dx = ev.clientX - startX;
                                const delta = dx / trackW; // 0~1 범위의 이동량
                                let newMin = Math.round((startMin + delta) * 100) / 100;
                                // 범위 제한
                                newMin = Math.max(0, Math.min(1 - gap, newMin));
                                const newMax = Math.round((newMin + gap) * 100) / 100;
                                setAdvancedFilters(f => ({ ...f, probMin: String(newMin), probMax: String(newMax) }));
                              };
                              const onUp = () => {
                                window.removeEventListener('mousemove', onMove);
                                window.removeEventListener('mouseup', onUp);
                              };
                              window.addEventListener('mousemove', onMove);
                              window.addEventListener('mouseup', onUp);
                            }}
                          />
                          <input
                            type="range" min="0" max="100" step="1"
                            value={Math.round(pMin * 100)}
                            onChange={e => {
                              const v = Number(e.target.value) / 100;
                              if (v < pMax) setAdvancedFilters(f => ({ ...f, probMin: String(v) }));
                            }}
                            onKeyDown={e => handleKey(e, 'min')}
                            className="absolute inset-x-0 w-full appearance-none bg-transparent pointer-events-none z-10
                              [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
                              [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-blue-500 [&::-webkit-slider-thumb]:border-2
                              [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:shadow-lg [&::-webkit-slider-thumb]:pointer-events-auto
                              [&::-webkit-slider-thumb]:cursor-grab [&::-webkit-slider-thumb]:active:cursor-grabbing
                              [&::-webkit-slider-thumb]:hover:bg-blue-400 [&::-webkit-slider-thumb]:transition-colors"
                            title={`최소: ${(pMin * 100).toFixed(0)}%`}
                          />
                          <input
                            type="range" min="0" max="100" step="1"
                            value={Math.round(pMax * 100)}
                            onChange={e => {
                              const v = Number(e.target.value) / 100;
                              if (v > pMin) setAdvancedFilters(f => ({ ...f, probMax: String(v) }));
                            }}
                            onKeyDown={e => handleKey(e, 'max')}
                            className="absolute inset-x-0 w-full appearance-none bg-transparent pointer-events-none z-20
                              [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
                              [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-purple-500 [&::-webkit-slider-thumb]:border-2
                              [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:shadow-lg [&::-webkit-slider-thumb]:pointer-events-auto
                              [&::-webkit-slider-thumb]:cursor-grab [&::-webkit-slider-thumb]:active:cursor-grabbing
                              [&::-webkit-slider-thumb]:hover:bg-purple-400 [&::-webkit-slider-thumb]:transition-colors"
                            title={`최대: ${(pMax * 100).toFixed(0)}%`}
                          />
                        </div>
                        <div className="flex items-center justify-between text-[10px]">
                          <span className="text-blue-400 font-bold">{(pMin * 100).toFixed(0)}%</span>
                          {isActive && (
                            <button
                              onClick={() => setAdvancedFilters(f => ({ ...f, probMin: '', probMax: '' }))}
                              className="text-slate-500 hover:text-slate-300 transition-colors"
                            >초기화</button>
                          )}
                          <span className="text-purple-400 font-bold">{(pMax * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                    );
                  })()}
                </div>

                {/* URL 유무 */}
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">URL 유무</label>
                  <div className="flex gap-2">
                    {(['all','yes','no'] as const).map(v => (
                      <button key={v}
                        onClick={() => setAdvancedFilters(f => ({ ...f, hasUrl: v }))}
                        className={`flex-1 py-1 rounded-lg text-xs font-bold border transition-all ${
                          advancedFilters.hasUrl === v
                            ? 'bg-blue-600 border-blue-500 text-white'
                            : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'
                        }`}
                      >
                        {v === 'all' ? '전체' : v === 'yes' ? 'URL 있음' : 'URL 없음'}
                      </button>
                    ))}
                  </div>
                </div>

                {/* 시그니처 유무 */}
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">시그니처 유무</label>
                  <div className="flex gap-2">
                    {(['all','yes','no'] as const).map(v => (
                      <button key={v}
                        onClick={() => setAdvancedFilters(f => ({ ...f, hasSignature: v }))}
                        className={`flex-1 py-1 rounded-lg text-xs font-bold border transition-all ${
                          advancedFilters.hasSignature === v
                            ? 'bg-blue-600 border-blue-500 text-white'
                            : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'
                        }`}
                      >
                        {v === 'all' ? '전체' : v === 'yes' ? '있음' : '없음'}
                      </button>
                    ))}
                  </div>
                </div>

                {/* 캐시 적용 타입 */}
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">적용 캐시 타입</label>
                  <select
                    title="캐시 적용 타입"
                    value={advancedFilters.cacheType}
                    onChange={e => setAdvancedFilters(f => ({ ...f, cacheType: e.target.value as typeof f.cacheType }))}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500 font-bold"
                  >
                    <option value="all">전체보기</option>
                    <option value="url_db">⚡ URL DB Cache 매칭</option>
                    <option value="url_runtime">⚡ URL Runtime Cache 매칭</option>
                    <option value="sig_db">⚡ SIG DB Cache 매칭</option>
                    <option value="sig_runtime">⚡ SIG Runtime Cache 매칭</option>
                  </select>
                </div>

              </div>
            </div>
          )}

          <div
            ref={logContainerRef}
            onScroll={handleScroll}
            className="flex-1 overflow-auto p-4 space-y-2"
          >
            {filteredLogs
              .map((logEntry, index, arr) => {
                const log = logEntry;
                const { cleanReason, note, isManual } = log.result ? parseReason(log.result.reason) : { cleanReason: "", note: null, isManual: false };
                const idx = log.originalIdx;
                const isFlagged = log.result?.flagged;

                const clusterId = logEntry.cluster_id;
                const prevClusterId = index > 0 ? arr[index - 1].cluster_id : null;
                const showHeader = isClusterViewMode && clusterId && clusterId !== prevClusterId;

                return (
                  <div key={idx} className="flex flex-col gap-2">
                    {showHeader && (
                      <div className="flex items-center gap-2 mt-6 mb-3 pl-2">
                         <div className="bg-indigo-500 w-1.5 h-6 rounded-full shadow-[0_0_8px_rgba(99,102,241,0.5)]"></div>
                         <h3 className="flex items-center gap-1.5 text-indigo-300 font-bold text-sm bg-indigo-900/30 px-3 py-1 rounded-md border border-indigo-700/50">
                           <span>유사 메시지 그룹 #{clusterId}</span>
                           <div className="flex items-center gap-1.5 ml-2 mt-[1px] text-[11px] font-medium font-sans">
                             <span className="bg-slate-800/80 text-slate-300 px-2 py-0.5 rounded border border-slate-700">
                               총 {clusterSizeMap.get(clusterId!) || 0}건
                             </span>
                             <span className="bg-red-500/15 text-red-400 px-2 py-0.5 rounded border border-red-500/30">
                               스팸 {clusterSpamMap.get(clusterId!) || 0}건
                             </span>
                             <span className="bg-green-600/15 text-green-400 px-2 py-0.5 rounded border border-green-600/30">
                               햄 {(clusterSizeMap.get(clusterId!) || 0) - (clusterSpamMap.get(clusterId!) || 0)}건
                             </span>
                           </div>
                         </h3>
                         <div className="h-px bg-slate-700/50 flex-1 ml-2"></div>
                      </div>
                    )}
                    <div id={`log-item-${idx + 1}`} className={`flex gap-4 items-start animate-fade-in group p-3 rounded-xl font-mono text-sm border transition-all duration-500 ${isFlagged ? 'bg-yellow-900/20 border-yellow-500/50 shadow-[0_0_15px_rgba(234,179,8,0.1)]' : (isClusterViewMode ? 'bg-slate-800/40 border-indigo-900/40 hover:bg-slate-800/60' : 'hover:bg-slate-800/50 border-transparent hover:border-slate-800/80')}`}>
                      <span className="text-slate-600 min-w-[30px] text-xs pt-1.5 font-bold">
                        {String(idx + 1).padStart(3, '0')}
                      </span>

                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        {log.result ? (
                          <>
                            {log.result.is_spam ? (
                              <span className="text-red-400 flex items-center gap-1 bg-red-400/10 px-1.5 rounded text-xs font-bold whitespace-nowrap">
                                <AlertCircle className="w-3 h-3" /> SPAM ({Math.round(log.result.spam_probability * 100)}%)
                                {((log.result.message_extracted_url && log.result.message_extracted_url.trim() && !log.result.drop_url) || (log.result.ibse_signature && log.result.ibse_signature.trim() && log.result.ibse_signature.toLowerCase() !== 'none')) && (
                                  <span className="text-red-300 ml-0.5">
                                    ({[
                                      ...(log.result.message_extracted_url && log.result.message_extracted_url.trim() && !log.result.drop_url ? ['URL'] : []),
                                      ...(log.result.ibse_signature && log.result.ibse_signature.trim() && log.result.ibse_signature.toLowerCase() !== 'none' ? ['SIGNATURE'] : [])
                                    ].join(', ')})
                                  </span>
                                )} - {getCodeDescription(log.result.classification_code)}
                              </span>
                            ) : (
                              <span className="text-green-400 flex items-center gap-1 bg-green-400/10 px-1.5 rounded text-xs font-bold whitespace-nowrap">
                                <CheckCircle className="w-3 h-3" /> HAM ({Math.round(log.result.spam_probability * 100)}%)
                              </span>
                            )}
                            {log.result.red_group && (
                               <span className="text-pink-400 flex items-center gap-1 bg-pink-400/10 px-1.5 py-0.5 rounded border border-pink-400/30 text-[10px] uppercase font-bold whitespace-nowrap drop-shadow-[0_0_8px_rgba(244,114,182,0.5)]" title="Red Group: 본문 HAM이나 단순 악성 URL 포함 격리">
                                 RED GROUP
                               </span>
                            )}
                            {/* 수정 버튼 */}
                            <button
                              onClick={() => openEditModal(idx, log)}
                              className="p-1 rounded hover:bg-slate-700 transition-colors text-slate-500 hover:text-yellow-400"
                              title="결과 수정"
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
                            {/* Flag 토글 버튼 */}
                            <button
                              onClick={() => toggleFlag(idx)}
                              className={`p-1.5 rounded transition-all flex items-center gap-1 font-bold text-xs border ${log.result.flagged ? 'text-yellow-400 bg-yellow-500/20 border-yellow-500/50 shadow-[0_0_10px_rgba(234,179,8,0.2)]' : 'text-slate-500 border-transparent hover:text-slate-300 hover:bg-slate-700'}`}
                              title={log.result.flagged ? "검토 대기중 (클릭하여 해제)" : "검토 필요 항목으로 표시"}
                            >
                              <Flag className={`w-3.5 h-3.5 ${log.result.flagged ? 'fill-yellow-400' : ''}`} />
                              {log.result.flagged && <span>검토대기</span>}
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

                      <div className="text-slate-300 break-all text-sm relative group pr-8">
                        {formatMessageWithLinks(log.message)}
                        {log.message && (
                          <button
                            onClick={() => {
                              navigator.clipboard.writeText(log.message);
                              const btn = document.getElementById(`copy-msg-${log.excel_row_number}`);
                              if (btn) {
                                btn.classList.replace('text-slate-500', 'text-green-400');
                                setTimeout(() => btn.classList.replace('text-green-400', 'text-slate-500'), 1500);
                              }
                            }}
                            className="absolute -top-1 right-0 p-1.5 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-800 rounded-md hover:bg-slate-700 active:scale-95 border border-slate-700 shadow-sm"
                            title="메시지 복사"
                          >
                            <Copy id={`copy-msg-${log.excel_row_number}`} className="w-3.5 h-3.5 text-slate-500 transition-colors" />
                          </button>
                        )}
                      </div>

                      {log.result && (
                        <div className="text-xs text-slate-500 mt-1 pl-2 border-l-2 border-slate-700 space-y-1.5">
                          <div className="text-slate-400 break-words">{cleanReason}</div>
                          
                          {/* URL 단위 1: 입력 파일 URL 필드 전용 분석 */}
                          {log.result.url_result?.details?.extracted_url && log.result.url_result.details.extracted_url !== "Unknown" && (
                            <div className="flex items-center gap-1.5 text-blue-400 border-l border-blue-500/30 pl-2 mt-1">
                              <span className="font-semibold border border-blue-400/30 bg-blue-400/10 px-1 py-0.5 rounded shadow-sm text-[10px] uppercase tracking-wider shrink-0" 
                                    title={isManual ? "단건 테스트 화면에서 URL Agent가 자체 추출한 URL입니다." : (log.result.pre_parsed_url ? "KISA 텍스트 파일의 URL 필드에서 입력받은 값을 분석한 결과입니다." : "입력 파일에 URL이 없어 AI가 본문에서 강제로 추출해 스크래핑한 결과입니다.")}>
                                {isManual ? "AI 자체 추출 URL (URL Agent)" : (log.result.pre_parsed_url ? "입력 URL 분석" : "본문 강제 추출 경로 분석")}
                              </span>
                              <span className="bg-slate-800/80 px-1.5 py-1 rounded text-slate-300 font-mono text-[11px] break-all border border-slate-700/50">
                                {log.result.drop_url ? (
                                  <>
                                     <span className="text-slate-500 mr-2 line-through opacity-70">
                                       {log.result.pre_parsed_url ? (
                                          log.result.pre_parsed_url
                                       ) : log.result.url_result.details.extracted_url && log.result.url_result.details.extracted_url !== "Unknown" ? (
                                          log.result.url_result.details.extracted_url
                                       ) : log.result.url_result.details.attempted_urls?.join(', ')}
                                     </span>
                                    {log.result.drop_url_reason === "obfuscation" ? (
                                        <span className="text-orange-400 font-semibold" title="난독화된 기형 URL(특수문자/한글 등)이 감지되어 추출 목록 대신 시그니처로 단독 추출되었습니다.">[난독화 URL 감지: 시그니처 추출]</span>
                                    ) : log.result.drop_url_reason === "safe_injection" ? (
                                        <span className="text-red-400 font-semibold" title="정상 도메인을 방패막이로 악용한 위장 URL로 판별되어 추출 목록에서 제외되었습니다.">[정상 도메인 위장 감지: 우회 방어]</span>
                                    ) : log.result.drop_url_reason === "bare_domain_decoy" ? (
                                        <span className="text-purple-400 font-semibold" title="대기업/정상 포털 등의 단독 도메인을 사칭/방패막이 목적으로 기재한 것으로 간주되어 추출 목록에서 제외되었습니다.">[단독 도메인: 사칭 방어 제외]</span>
                                    ) : (log.result.drop_url_reason === "anti_hallucination" || log.result.drop_url_reason === "hidden_url") ? (
                                        <span className="text-emerald-500 font-semibold" title="스패머가 의도적으로 숨긴 URL을 추적하여 검사했으며, 데이터 정합성을 위해 엑셀에는 저장하지 않습니다.">[숨김 URL 추적 완료: 엑셀 제외]</span>
                                    ) : (
                                        <span className="text-slate-400 font-semibold" title="접속 불가하거나 불완전한 URL로 판별되어 추출 목록에서 제외/대체되었습니다.">[불완전 URL: 추출 제외]</span>
                                    )}
                                  </>
                                ) : (
                                  <>
                                    {/* 1. 우선적으로 KISA 입력 URL 노출 */}
                                    {log.result.pre_parsed_url && (
                                      <span className="mr-1">
                                        {log.result.pre_parsed_url.split(',').map((u: string, i: number) => {
                                          const tu = u.trim();
                                          if (!tu) return null;
                                          return (
                                            <span key={`pre-${i}`}>
                                              {i > 0 && ", "}
                                              <a href={tu.startsWith('http') ? tu : `http://${tu}`} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 hover:underline transition-colors cursor-pointer">{tu}</a>
                                            </span>
                                          );
                                        })}
                                      </span>
                                    )}
                                    
                                    {/* 2. 입력 URL이 없을 경우 본문 강제 추출 URL 노출 */}
                                    {!log.result.pre_parsed_url && log.result.url_result.details.extracted_url && log.result.url_result.details.extracted_url !== "Unknown" && (
                                      <span className="mr-1">
                                        {log.result.url_result.details.extracted_url.split(',').map((u: string, i: number) => {
                                          const tu = u.trim();
                                          if (!tu) return null;
                                          return (
                                            <span key={`ext-${i}`}>
                                              {i > 0 && ", "}
                                              <a href={tu.startsWith('http') ? tu : `http://${tu}`} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 hover:underline transition-colors cursor-pointer">{tu}</a>
                                            </span>
                                          );
                                        })}
                                      </span>
                                    )}

                                    {/* 3. 리다이렉트 등으로 인한 최종 도착지가 다를 경우 명시 */}
                                    {log.result.url_result.details.final_url && log.result.url_result.details.final_url !== "Unknown" && !log.result.pre_parsed_url?.includes(log.result.url_result.details.final_url) && !log.result.url_result.details.extracted_url?.includes(log.result.url_result.details.final_url) && (
                                        <span className="text-slate-400 ml-1">→ <a href={log.result.url_result.details.final_url.startsWith('http') ? log.result.url_result.details.final_url : `http://${log.result.url_result.details.final_url}`} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 hover:underline transition-colors cursor-pointer">{log.result.url_result.details.final_url}</a></span>
                                    )}

                                    {/* 4. 백엔드 시도/탐색 이력(attempted_urls)을 부가 정보로 노출 */}
                                    {log.result.url_result.details.attempted_urls && log.result.url_result.details.attempted_urls.length > 0 && (
                                      <span className="text-slate-500/70 text-[10px] ml-2 font-sans tracking-tight" title="백엔드 요원이 접속을 시도하거나 리다이렉트를 추적한 전체 탐색 이력입니다.">
                                        (탐색: {log.result.url_result.details.attempted_urls.join(' → ')})
                                      </span>
                                    )}
                                  </>
                                )}
                              </span>
                            </div>
                          )}

                          {/* URL 단위 2: 메시지 본문 직접 추출 */}
                          {log.result.message_extracted_url && log.result.message_extracted_url !== "" && (
                            <div className="flex items-center gap-1.5 text-emerald-400 border-l border-emerald-500/30 pl-2 mt-1">
                              <span className="font-semibold border border-emerald-400/30 bg-emerald-400/10 px-1 py-0.5 rounded shadow-sm text-[10px] uppercase tracking-wider shrink-0" title="메시지 본문 내용에서 AI가 직접 텍스트를 분석하여 추출/복원한 URL입니다.">
                                본문 추출 URL
                              </span>
                              <span className="bg-slate-800/80 px-1.5 py-1 rounded text-slate-300 font-mono text-[11px] break-all border border-slate-700/50">
                                {log.result.message_extracted_url.split(',').map((urlStr: string, i: number) => {
                                  const trimmedUrl = urlStr.trim();
                                  if (!trimmedUrl) return null;
                                  return (
                                    <span key={i}>
                                      {i > 0 && ", "}
                                      <a href={trimmedUrl.startsWith('http') ? trimmedUrl : `http://${trimmedUrl}`} target="_blank" rel="noopener noreferrer" className="text-emerald-400 hover:text-emerald-300 hover:underline transition-colors cursor-pointer">
                                        {trimmedUrl}
                                      </a>
                                    </span>
                                  );
                                })}
                              </span>
                            </div>
                          )}

                          {/* 시그니처 출력 보장 */}
                          {log.result.ibse_signature && (
                            <div className="flex items-center gap-1.5 text-indigo-400 border-l border-indigo-500/30 pl-2">
                              <span className="font-semibold border border-indigo-400/30 bg-indigo-400/10 px-1 py-0.5 rounded shadow-sm text-[10px] uppercase tracking-wider shrink-0">
                                시그니처
                              </span>
                              <span className="bg-slate-800/80 px-1.5 py-1 rounded text-slate-300 font-mono text-[11px] break-all border border-slate-700/50 flex items-center flex-wrap gap-1">
                                <span>{log.result.ibse_signature}</span>
                                {log.result.ibse_signature.toLowerCase() !== 'none' && (
                                  <span className="text-[10px] text-slate-500 tracking-tighter shrink-0 font-sans font-semibold">
                                    ({[...log.result.ibse_signature].reduce((acc, char) => acc + (char.charCodeAt(0) > 127 ? 2 : 1), 0)} byte)
                                  </span>
                                )}
                              </span>
                            </div>
                          )}
                          
                          {(isManual || note) && (
                            <div className="flex items-center gap-2 text-emerald-400/80 pt-1">
                              <User className="w-3 h-3" />
                              {note ? <span>{note}</span> : <span>Manual Decision</span>}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
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

              {/* Input URL Field */}
              <div>
                <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">입력 파일 URL (수동/테스트용 지시)</label>
                <input
                  type="text"
                  value={inputUrl}
                  onChange={(e) => setInputUrl(e.target.value)}
                  className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="원본에 URL이 없는 경우 시험용으로 직접 타이핑할 수 있습니다."
                />
              </div>

              {/* Status Grid */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">판정</label>
                  <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800">
                    <button
                      onClick={() => {
                          const newReason = editingLog.reason ? `[수동 SPAM 전환] ${editingLog.reason.replace(/\[수동 HAM 전환\]\s*/g, '')}` : '[수동 SPAM 전환]';
                          setEditingLog({ ...editingLog, is_spam: true, classification_code: editingLog.classification_code || '1', reason: newReason });
                        }}
                      className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${editingLog.is_spam
                        ? 'bg-rose-500/20 text-rose-400 shadow-sm'
                        : 'text-slate-500 hover:text-slate-300'
                        }`}
                    >
                      SPAM
                    </button>
                    <button
                      onClick={() => {
                          let newReason = editingLog.reason ? `[수동 HAM 전환] ${editingLog.reason.replace(/\[수동 SPAM 전환\]\s*/g, '')}` : '[수동 HAM 전환]';
                          newReason = newReason.replace(/\[수동 Red Group 지정\]\s*\|?\s*/g, '');
                          newReason = newReason.replace(/\[텍스트 HAM \+ 악성 URL 분리 감지[^\]]*\]\s*\|?\s*/g, '');
                          newReason = newReason.replace(/\[URL SPAM[^\]]*\]\s*\|?\s*/g, '');
                          newReason = newReason.replace(/\|\s*$/, '').trim();
                          setEditingLog({ ...editingLog, is_spam: false, classification_code: '', red_group: false, reason: newReason, malicious_url_extracted: false, drop_url: false, drop_url_reason: null });
                        }}
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
                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">분류 코드 & RED GROUP</label>
                    <div className="flex gap-2">
                        <select
                          value={editingLog.classification_code}
                          onChange={(e) => setEditingLog({ ...editingLog, classification_code: e.target.value })}
                          className="flex-1 px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all appearance-none"
                        >
                          <option value="0">0 - 기타 스팸</option>
                          <option value="1">1 - 유해성 스팸</option>
                          <option value="2">2 - 사기/투자 스팸</option>
                          <option value="3">3 - 불법 도박/대출</option>
                        </select>
                        <button
                          onClick={() => {
                            if (!inputUrl) return; // URL 없으면 동작 차단
                            const isTurningOn = !editingLog.red_group;
                            let newReason = editingLog.reason || '';
                            if (isTurningOn && !newReason.includes('[수동 Red Group 지정]')) {
                              newReason = `[수동 Red Group 지정] ${newReason}`;
                            } else if (!isTurningOn) {
                              newReason = newReason.replace(/\[수동 Red Group 지정\]\s*/g, '');
                            }
                            setEditingLog({ ...editingLog, red_group: isTurningOn, reason: newReason });
                          }}
                          disabled={!inputUrl}
                          title={!inputUrl ? 'URL이 없는 항목은 Red Group 지정 불가' : '악성 위험 수위가 높은 스팸 (Red Group 지정)'}
                          className={`px-4 py-3 rounded-xl border text-sm font-bold transition-all flex items-center justify-center gap-2 ${
                            !inputUrl
                              ? 'bg-slate-900 border-slate-800 text-slate-600 cursor-not-allowed opacity-40'
                              : editingLog.red_group
                                ? 'bg-rose-500/20 border-rose-500/50 text-rose-500'
                                : 'bg-slate-950 border-slate-800 text-slate-500 hover:text-slate-300'
                          }`}
                        >
                           🔥 RED 
                        </button>
                    </div>
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

              {/* 시그니처 추출 - SPAM 항목에서만 표시 */}
              {editingLog.is_spam && (
                <div>
                  <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">시그니처 (IBSE)</label>
                  <div className="flex gap-2 items-stretch">
                    <textarea
                      value={extractedSignature}
                      onChange={(e) => setExtractedSignature(e.target.value)}
                      placeholder="시그니처 없음 (문자열셋팅 또는 추출 버튼으로 생성)"
                      rows={4}
                      className="flex-1 px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-white text-[13px] font-mono leading-relaxed focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all placeholder-slate-600 resize-y min-h-[96px]"
                    />
                    <div className="flex flex-col gap-2 w-36 shrink-0">
                      <button
                        onClick={() => setExtractedSignature((editingLog?.message || '').replace(/\s/g, ''))}
                        title="본문의 공백을 모두 제거하여 시그니처 편집창으로 가져옵니다."
                        className="flex-1 px-3 py-2 rounded-xl border text-xs font-bold transition-all flex justify-center items-center gap-1.5 bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-700 hover:text-white whitespace-nowrap"
                      >
                        📄 문자열 원본가져오기
                      </button>
                      <button
                        onClick={handleExtractSignature}
                        disabled={isExtracting}
                        className="flex-1 px-3 py-2 rounded-xl border text-xs font-bold transition-all flex justify-center items-center gap-1.5 bg-slate-800 border-slate-700 text-indigo-400 hover:bg-slate-700 hover:text-indigo-300 disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
                      >
                        {isExtracting ? (
                          <><span className="animate-spin">⟳</span> 추출 중...</>
                        ) : (
                          <>🔬 AI 시그니처 추출</>
                        )}
                      </button>
                    </div>
                  </div>
                  {extractedSignature && (
                    <p className="mt-1.5 text-xs text-slate-500">
                      바이트 길이: {[...(extractedSignature || '')].reduce((acc, ch) => acc + (ch.charCodeAt(0) > 127 ? 2 : 1), 0)}byte
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Footer / Wizard Logic */}
            {wizardStep === 1 ? (
              <div className="flex gap-3 px-8 py-5 border-t border-slate-800 bg-slate-900">
                <button
                  onClick={() => { setEditModalOpen(false); setEditingLog(null); }}
                  className="flex-1 py-3.5 rounded-2xl bg-slate-800 text-slate-300 font-bold hover:bg-slate-700 transition-all"
                >
                  취소
                </button>
                <button
                  onClick={handleFirstStepSave}
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
                      {(!logs[editingLog.index]?.result?.is_spam && editingLog.is_spam) ? '다음 단계 (연쇄 작업) 👉' : '저장'}
                    </>
                  )}
                </button>
              </div>
            ) : (
              <div className="flex flex-col px-8 py-5 border-t border-slate-800 bg-slate-900 space-y-4">
                  <div className="p-4 bg-indigo-950/30 border border-indigo-500/20 text-indigo-200 rounded-xl">
                      <p className="text-sm font-bold mb-1">🚨 [HAM → SPAM] 추가 데이터 페칭</p>
                      <p className="text-xs opacity-80 mb-4">엑셀 시트(중복 제거 등) 동기화를 위해 URL/시그니처를 추출합니다.</p>
                      
                      <div className="space-y-3">
                          <div className="flex items-center gap-3">
                              <button 
                                onClick={handleExtractUrl} 
                                disabled={isUrlExtracting || editingLog.red_group} 
                                title={editingLog.red_group ? "Red Group은 본문 추출이 금지됩니다." : ""}
                                className={`px-3 py-2 rounded text-xs font-bold transition-all w-28 text-center border flex justify-center items-center ${editingLog.red_group ? 'bg-slate-900 border-slate-800 text-slate-600 cursor-not-allowed' : 'bg-slate-800 text-slate-300 hover:bg-slate-700 border-slate-700'}`}
                              >
                                  {isUrlExtracting ? <Loader2 className="w-3 h-3 animate-spin"/> : 'URL 추출'}
                              </button>
                              <div className="flex-1 flex gap-2 overflow-x-auto custom-scrollbar">
                                  {editingLog.red_group ? (
                                      inputUrl ? (
                                          <span className="text-xs px-2 py-1 bg-pink-950/50 border border-pink-900/50 rounded text-pink-300 whitespace-nowrap truncate" title="Red Group: 입력 파일 URL 사용">{inputUrl}</span>
                                      ) : (
                                          <span className="text-xs text-slate-600 italic mt-1">상단 '입력 파일 URL'에서 타이핑해주세요.</span>
                                      )
                                  ) : (
                                      extractedUrls.length > 0 ? extractedUrls.map(u => <span key={u} className="text-xs px-2 py-1 bg-slate-950/50 rounded text-blue-300 whitespace-nowrap">{u}</span>) : (
                                          inputUrl ? (
                                              <span className="text-xs px-2 py-1 bg-slate-800 border border-slate-700/50 rounded text-slate-400 whitespace-nowrap truncate shadow-inner flex items-center gap-1" title="본문 추출 URL이 없어 상단 입력 URL이 대체 사용됩니다.">
                                                <span className="opacity-50 text-[10px]">🔗대체:</span> {inputUrl}
                                              </span>
                                          ) : (
                                              <span className="text-xs text-slate-500 italic mt-1">없음</span>
                                          )
                                      )
                                  )}
                              </div>
                          </div>
                          
                          <div className="flex items-center gap-3">
                              <button onClick={handleExtractSignature} disabled={isExtracting} className="px-3 py-2 bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 rounded hover:bg-indigo-600/40 text-xs font-bold transition-all min-w-[112px] whitespace-nowrap text-center flex justify-center items-center">
                                  {isExtracting ? <Loader2 className="w-3 h-3 animate-spin"/> : '✨ LLM 시그니처'}
                              </button>
                              <input 
                                  type="text" 
                                  value={extractedSignature} 
                                  onChange={e=>setExtractedSignature(e.target.value)} 
                                  className="flex-1 bg-slate-950 border border-slate-800 text-white rounded px-3 py-1.5 text-xs focus:ring-1 focus:ring-indigo-500 outline-none" 
                                  placeholder="사전 추출된 시그니처가 없으면 빈칸으로 저장됩니다." 
                              />
                          </div>
                      </div>
                  </div>

                  <div className="flex gap-3">
                      <button onClick={() => setWizardStep(1)} className="w-[120px] py-3.5 rounded-2xl bg-slate-800 text-slate-300 font-bold hover:bg-slate-700 transition-all flex justify-center items-center">이전</button>
                      <button onClick={saveEdit} disabled={editSaving} className="flex-1 py-3.5 rounded-2xl bg-rose-600 text-white font-bold hover:bg-rose-500 transition-all shadow-lg flex items-center justify-center gap-2">
                          {editSaving ? <><Loader2 className="w-5 h-5 animate-spin" /> 저장 중...</> : <><Save className="w-5 h-5" /> 최종 연쇄 동기화 저장</>}
                      </button>
                  </div>
              </div>
            )}
          </div>
        </div>
      )}
      </div> {/* End Main Content Area */}

      {/* AI Chat Side Panel */}
      <div 
        style={{ width: isChatOpen ? chatWidth : 0 }}
        className={`relative h-full bg-slate-900 border-l border-slate-700 shadow-[inset_10px_0_30px_rgba(0,0,0,0.5)] z-30 flex flex-col flex-shrink-0 overflow-hidden ${isChatDragging ? 'transition-none' : 'transition-[width] duration-300 ease-in-out'}`}
      >
        {/* Resize Handle (Hitbox) */}
        {isChatOpen && (
          <div
            onMouseDown={handleChatResizeMouseDown}
            className="absolute left-0 top-0 w-8 h-full cursor-col-resize -translate-x-1/2 flex items-center justify-center group z-[60]"
          >
            <div className={`h-full w-1 transition-colors ${isChatDragging ? 'bg-indigo-500' : 'group-hover:bg-indigo-500/50'}`} />
            <div className={`absolute h-16 w-1 rounded-full transition-colors ${isChatDragging ? 'bg-white' : 'bg-slate-600 group-hover:bg-white'}`} />
          </div>
        )}
        <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-900/90 backdrop-blur">
          <div className="flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-indigo-400" />
            <h2 className="font-bold text-slate-200">AI 스팸 검증 챗봇</h2>
          </div>
          <button 
            onClick={() => setIsChatOpen(false)}
            className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="flex-1 overflow-hidden relative">
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
      </div>

      {/* Chat FAB */}
      {!isChatOpen && (
        <button
          onClick={() => setIsChatOpen(true)}
          className="fixed bottom-6 right-6 w-14 h-14 bg-indigo-600 hover:bg-indigo-500 text-white rounded-full shadow-[0_0_20px_rgba(79,70,229,0.4)] flex items-center justify-center z-30 transition-all hover:scale-105 active:scale-95 group"
          title="AI 스팸 검증 챗봇 열기"
        >
          <MessageSquare className="w-6 h-6 group-hover:animate-pulse" />
          {hitlRequest && (
            <span className="absolute top-0 right-0 w-4 h-4 bg-rose-500 rounded-full border-2 border-indigo-600 animate-bounce" />
          )}
        </button>
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

      <DatabaseManagerModal
        isOpen={isDbManagerOpen}
        onClose={() => setIsDbManagerOpen(false)}
      />

      <SignatureRefinerModal
        isOpen={isRefinerModalOpen}
        onClose={() => setIsRefinerModalOpen(false)}
        reportFilename={activeReportFileName || downloadFilename || 'realtime_report.json'}
        logs={logs}
        onApplySuccess={() => {
           if (activeReportFileName) {
               reloadReportFromServer(activeReportFileName);
           }
        }}
        onApplyModified={(modified) => {
           // 서버 파일 없이 인메모리로 적용된 수정 엔트리를 React 상태에 직접 반영
           setLogs(prev => {
             const newLogs = { ...prev };
             for (const [logId, entry] of Object.entries(modified)) {
               const numKey = Number(logId);
               if (numKey in newLogs) {
                 newLogs[numKey] = { ...newLogs[numKey], result: (entry as Record<string, unknown>).result };
               }
             }
             return newLogs;
           });
        }}
      />

      {/* 엑셀 재생성 오버레이 */}
      {isRegeneratingExcel && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-indigo-500/30 rounded-2xl p-8 flex flex-col items-center gap-5 max-w-sm w-full mx-4 shadow-2xl shadow-indigo-500/10">
            <div className="relative">
              <div className="absolute inset-0 bg-indigo-500/20 rounded-full blur-xl animate-pulse"></div>
              <Loader2 className="w-12 h-12 text-indigo-400 animate-spin relative z-10" />
            </div>
            <div className="text-center space-y-2">
              <h3 className="text-lg font-bold text-white tracking-tight">수정본 엑셀 재생성 중...</h3>
              <p className="text-sm text-slate-400 leading-relaxed">
                 화면의 최신 결과를 바탕으로 엑셀 파일을 백지부터 완벽하게 새로 짜맞추고 있습니다.<br/>
                 <span className="text-indigo-300 font-medium mt-1 inline-block">수 초 가량 소요될 수 있습니다.</span>
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 중지 확인 커스텀 모달 */}
      {cancelConfirmOpen && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-800 rounded-2xl shadow-2xl p-6 w-full max-w-sm border border-slate-700 animate-in slide-in-from-bottom-4 duration-300">
            <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2 mb-3">
              <span className="text-yellow-500">⚠️</span> 중지 확인
            </h3>
            <p className="text-sm text-slate-300 mb-6 leading-relaxed">
              즉시 중지되지 않으며,<br/>
              현재 처리 중인 배치(최대 20개 메시지)가 <br/>
              완료된 후 최종 중지됩니다.<br/><br/>
              계속하시겠습니까?
            </p>
            <div className="flex gap-3 justify-end mt-2">
              <button
                onClick={() => setCancelConfirmOpen(false)}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg text-sm transition-colors border border-slate-600"
              >
                닫기
              </button>
              <button
                onClick={confirmCancel}
                className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg text-sm font-bold shadow-lg shadow-red-500/20 transition-colors border border-red-600"
              >
                중지하기
              </button>
            </div>
          </div>
        </div>
      )}

      {isValidationModalOpen && (
        <ValidationModal
          logs={logs}
          onClose={() => setIsValidationModalOpen(false)}
        />
      )}
    </div>
  );
}
export default App;
