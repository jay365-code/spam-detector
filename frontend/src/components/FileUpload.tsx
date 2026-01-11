import React, { useCallback, useState, useRef } from 'react';
import { UploadCloud, FileSpreadsheet, Loader2, CheckCircle } from 'lucide-react';

interface FileUploadProps {
    clientId: string;
    onUploadStart: () => void;
    onUploadComplete: (filename: string) => void;
    onFileSelect?: () => void;
}

export const FileUpload: React.FC<FileUploadProps> = ({ clientId, onUploadStart, onUploadComplete, onFileSelect }) => {
    const [isDragOver, setIsDragOver] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadStatus, setUploadStatus] = useState<'idle' | 'selected' | 'uploading' | 'success' | 'error'>('idle');
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [fileName, setFileName] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(true);
    }, []);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
    }, []);

    const processFile = useCallback((file: File) => {
        if (!file) return;
        const validExtensions = ['.xlsx', '.txt'];
        const isValid = validExtensions.some(ext => file.name.toLowerCase().endsWith(ext));

        if (!isValid) {
            alert("Please upload an Excel file (.xlsx) or Text file (.txt)");
            return;
        }
        setSelectedFile(file);
        setFileName(file.name);
        setUploadStatus('selected');
        onFileSelect?.();
    }, [onFileSelect]);

    const handleStartUpload = async () => {
        if (!selectedFile) return;

        setIsUploading(true);
        setUploadStatus('uploading');
        onUploadStart();

        const formData = new FormData();
        formData.append('file', selectedFile);
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
            console.log('Upload success:', data);
            setUploadStatus('success');
            onUploadComplete(data.filename);

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
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            processFile(files[0]);
        }
    }, [processFile]);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            processFile(e.target.files[0]);
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
                onChange={handleFileSelect}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20"
                disabled={isUploading || uploadStatus === 'selected'}
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
                    <div className="flex items-center gap-4 z-30 w-full justify-between px-4">
                        <div className="flex items-center gap-3">
                            <div className="p-2 bg-green-500/20 rounded-full">
                                <FileSpreadsheet className="w-5 h-5 text-green-400" />
                            </div>
                            <div>
                                <p className="text-sm font-medium text-white">{fileName}</p>
                                <p className="text-xs text-slate-400">Ready to analyze</p>
                            </div>
                        </div>
                        <div className="flex gap-2">
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    setUploadStatus('idle');
                                    setSelectedFile(null);
                                    setFileName(null);
                                }}
                                className="px-3 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 rounded text-slate-200"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleStartUpload();
                                }}
                                className="px-4 py-1.5 text-xs bg-blue-500 hover:bg-blue-600 rounded text-white font-semibold shadow-lg shadow-blue-500/20 animate-pulse"
                            >
                                Start Analysis
                            </button>
                        </div>
                    </div>
                )}

                {uploadStatus === 'uploading' && (
                    <div className="flex items-center gap-3 animate-pulse">
                        <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
                        <span className="text-sm text-blue-300 font-medium">Processing {fileName}...</span>
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
                                setFileName(null);
                                setSelectedFile(null);
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
