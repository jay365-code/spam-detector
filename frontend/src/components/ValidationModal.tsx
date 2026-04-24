import React, { useState, useRef } from 'react';
import { X, CheckCircle, Loader2, Download, FileText } from 'lucide-react';
import { API_BASE } from '../config';

interface ValidationModalProps {
  logs: Record<number, unknown>;
  onClose: () => void;
}

export const ValidationModal: React.FC<ValidationModalProps> = ({ logs, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [reportMd, setReportMd] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const excelInputRef = useRef<HTMLInputElement>(null);

  const handleValidate = async () => {
    setLoading(true);
    setError(null);
    setReportMd(null);
    setDownloadUrl(null);

    try {
      const formData = new FormData();
      const logsBlob = new Blob([JSON.stringify(Object.values(logs))], { type: 'application/json' });
      formData.append('logs_file', logsBlob, 'logs.json');

      if (excelInputRef.current?.files?.[0]) {
        formData.append('excel_file', excelInputRef.current.files[0]);
      }

      const res = await fetch(`${API_BASE}/api/utils/validate-report`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) throw new Error(`서버 오류: ${res.status}`);
      const data = await res.json();

      setReportMd(data.report_md ?? '검증 완료');
      setDownloadUrl(data.download_url ?? null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center gap-2 text-amber-400 font-semibold">
            <CheckCircle className="w-5 h-5" />
            작업 퀄리티 검증
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 flex flex-col gap-4 overflow-y-auto flex-1">
          <div className="flex flex-col gap-2">
            <label className="text-sm text-slate-300">엑셀 파일 첨부 (선택)</label>
            <input
              ref={excelInputRef}
              type="file"
              accept=".xlsx"
              className="text-sm text-slate-300 file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:bg-slate-700 file:text-slate-200"
            />
          </div>

          <button
            onClick={handleValidate}
            disabled={loading || Object.keys(logs).length === 0}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 rounded-lg text-white font-medium transition-colors"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
            {loading ? '검증 중...' : '검증 실행'}
          </button>

          {error && (
            <div className="text-red-400 text-sm bg-red-900/20 border border-red-800 rounded p-3">{error}</div>
          )}

          {reportMd && (
            <div className="flex flex-col gap-2">
              {downloadUrl && (
                <a
                  href={`${API_BASE}${downloadUrl}`}
                  className="flex items-center gap-2 text-sm text-blue-400 hover:text-blue-300"
                  download
                >
                  <Download className="w-4 h-4" /> 검증 리포트 다운로드
                </a>
              )}
              <div className="bg-slate-800 rounded-lg p-3 text-sm text-slate-200 whitespace-pre-wrap font-mono overflow-x-auto border border-slate-700">
                <div className="flex items-center gap-1 text-xs text-slate-400 mb-2">
                  <FileText className="w-3 h-3" /> 검증 결과
                </div>
                {reportMd}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
