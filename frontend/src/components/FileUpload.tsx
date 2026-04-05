import React, { useCallback, useState, useRef } from 'react';
import { UploadCloud, FileSpreadsheet, Loader2, CheckCircle } from 'lucide-react';

interface FileUploadProps {
    clientId: string;
    onUploadStart: () => void;
    onUploadComplete: (filename: string, kisaFilename?: string, trapFilename?: string) => void;
    onFileSelect?: () => void;
}

export const FileUpload: React.FC<FileUploadProps> = ({ clientId, onUploadStart, onUploadComplete, onFileSelect }) => {
    const [isDragOver, setIsDragOver] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadStatus, setUploadStatus] = useState<'idle' | 'selected' | 'uploading' | 'success' | 'error' | 'cancelled'>('idle');
    const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
    const [fileNames, setFileNames] = useState<string>("");
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(true);
    }, []);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
    }, []);

    const processFiles = useCallback((files: FileList | File[]) => {
        if (!files || files.length === 0) return;
        const validExtensions = ['.xlsx', '.txt'];
        const validFiles = Array.from(files).filter(file => 
            validExtensions.some(ext => file.name.toLowerCase().endsWith(ext))
        );

        if (validFiles.length === 0) {
            alert("Please upload Excel (.xlsx) or Text (.txt) files");
            return;
        }
        
        setSelectedFiles(prev => {
            const existingNames = new Set(prev.map(f => f.name));
            const newFiles = validFiles.filter(f => !existingNames.has(f.name));
            const combined = [...prev, ...newFiles];
            setFileNames(combined.map(f => f.name).join(', '));
            return combined;
        });
        
        setUploadStatus('selected');
        onFileSelect?.();
        
        // input value 초기화하여 같은 파일을 지웠다가 다시 선택할 수 있도록 함
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    }, [onFileSelect]);

    const handleStartUpload = async () => {
        if (selectedFiles.length === 0) return;

        setIsUploading(true);
        setUploadStatus('uploading');
        onUploadStart();

        const formData = new FormData();
        selectedFiles.forEach(file => {
            formData.append('files', file); // files[] is usually matched by List[UploadFile] using form keys
        });
        formData.append('client_id', clientId);

        try {
            const response = await fetch('http://localhost:8000/upload', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error('Upload failed');
            }

            const data = await response.json();
            console.log('Upload response:', data);
            if (data.status === 'cancelled') {
                setUploadStatus('cancelled');
                // onUploadComplete 호출 안 함 → 기존 결과(로그) 유지
            } else {
                setUploadStatus('success');
                onUploadComplete(data.filename, data.kisa_filename, data.trap_filename);
            }

        } catch (error) {
            console.error('Error uploading file:', error);
            setUploadStatus('error');
        } finally {
            setIsUploading(false);
        }
    };

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
        if (e.dataTransfer.files.length > 0) {
            processFiles(e.dataTransfer.files);
        }
    }, [processFiles]);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            processFiles(e.target.files);
        }
    };

    return (
        <div
            className={`relative w-full max-w-2xl mx-auto p-2 rounded-xl transition-all duration-300 border border-slate-700
        ${isDragOver
                    ? 'bg-blue-500/20 border-blue-500'
                    : 'bg-slate-800/30 hover:bg-slate-800/50'
                }
        ${isUploading ? 'opacity-80 pointer-events-none' : ''}
      `}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
        >
            <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.txt"
                multiple
                onChange={handleFileSelect}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20"
                disabled={isUploading}
            />

            <div className="flex items-center justify-center gap-4 text-slate-300 py-2 min-h-[60px]">

                {uploadStatus === 'idle' && (
                    <>
                        <UploadCloud className={`w-8 h-8 text-blue-400 transition-transform ${isDragOver ? 'scale-110' : ''}`} />
                        <div className="text-left">
                            <h3 className="text-base font-semibold text-white">Upload File (Excel/Txt)</h3>
                            <p className="text-xs text-slate-400">Drag & drop or Click</p>
                        </div>
                    </>
                )}

                {uploadStatus === 'selected' && (
                    <div className="flex flex-col gap-2 z-30 w-full px-4 py-2 pointer-events-auto">
                        <div className="max-h-32 overflow-y-auto pr-1">
                            {selectedFiles.map((file, idx) => (
                                <div key={idx} className="flex items-center justify-between bg-slate-800/80 p-2 mb-1.5 rounded border border-slate-700 hover:border-slate-600 transition-colors">
                                    <div className="flex items-center gap-3 min-w-0">
                                        <div className="p-1 bg-green-500/20 rounded">
                                            <FileSpreadsheet className="w-4 h-4 text-green-400" />
                                        </div>
                                        <p className="text-sm font-medium text-white truncate max-w-[300px]" title={file.name}>
                                            {file.name}
                                        </p>
                                    </div>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            const newFiles = selectedFiles.filter((_, i) => i !== idx);
                                            setSelectedFiles(newFiles);
                                            setFileNames(newFiles.map(f => f.name).join(', '));
                                            if (newFiles.length === 0) setUploadStatus('idle');
                                        }}
                                        className="p-1 hover:bg-red-500/20 rounded text-slate-400 hover:text-red-400 transition-colors"
                                        title="Remove file"
                                    >
                                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                        </svg>
                                    </button>
                                </div>
                            ))}
                        </div>

                        <div className="flex gap-2 justify-end mt-1">
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    fileInputRef.current?.click();
                                }}
                                className="px-3 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 rounded text-slate-200 border border-slate-600 z-30"
                            >
                                + Add More
                            </button>
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    setUploadStatus('idle');
                                    setSelectedFiles([]);
                                    setFileNames("");
                                }}
                                className="px-3 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 rounded text-slate-200 z-30"
                            >
                                Clear All
                            </button>
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleStartUpload();
                                }}
                                className="px-4 py-1.5 text-xs bg-blue-500 hover:bg-blue-600 rounded text-white font-semibold shadow-lg shadow-blue-500/20 animate-pulse"
                            >
                                Start Analysis ({selectedFiles.length})
                            </button>
                        </div>
                    </div>
                )}

                {uploadStatus === 'uploading' && (
                    <div className="flex items-center gap-3 animate-pulse">
                        <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
                        <span className="text-sm text-blue-300 font-medium">Processing {fileNames}...</span>
                    </div>
                )}

                {uploadStatus === 'success' && (
                    <div className="flex items-center gap-3">
                        <CheckCircle className="w-5 h-5 text-green-400" />
                        <span className="text-sm text-green-300 font-medium">Done! Check logs.</span>
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                setUploadStatus('idle');
                                setFileNames("");
                                setSelectedFiles([]);
                                onFileSelect?.();
                                if (fileInputRef.current) {
                                    fileInputRef.current.value = '';
                                    fileInputRef.current.click();
                                }
                            }}
                            className="ml-2 px-3 py-1 text-xs bg-slate-700/50 hover:bg-slate-700 rounded text-slate-400 z-30"
                        >
                            New Upload
                        </button>
                    </div>
                )}

                {uploadStatus === 'cancelled' && (
                    <div className="flex items-center gap-3">
                        <FileSpreadsheet className="w-5 h-5 text-amber-400" />
                        <span className="text-sm text-amber-300">중지됨 (기존 결과 유지)</span>
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                setUploadStatus('idle');
                                setSelectedFiles([]);
                                setFileNames("");
                                onFileSelect?.();
                            }}
                            className="px-3 py-1 text-xs bg-slate-700 hover:bg-slate-600 rounded text-white z-30"
                        >
                            새 파일
                        </button>
                    </div>
                )}

                {uploadStatus === 'error' && (
                    <div className="flex items-center gap-3">
                        <FileSpreadsheet className="w-5 h-5 text-red-400" />
                        <span className="text-sm text-red-400">Failed</span>
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                setUploadStatus('idle');
                            }}
                            className="px-3 py-1 text-xs bg-slate-700 hover:bg-slate-600 rounded text-white z-30"
                        >
                            Retry
                        </button>
                    </div>
                )}

            </div>
        </div>
    );
};
