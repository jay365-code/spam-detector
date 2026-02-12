import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Folder, HardDrive, CornerLeftUp, Check, X, Loader2, FolderOpen } from 'lucide-react';

interface FolderListResponse {
    current_path: string;
    folders: string[];
    is_root: boolean;
    parent_path: string | null;
}

interface FolderPickerModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSelect: (path: string) => void;
    initialPath?: string;
}

export const FolderPickerModal: React.FC<FolderPickerModalProps> = ({ isOpen, onClose, onSelect, initialPath }) => {
    const [currentPath, setCurrentPath] = useState(initialPath || '');
    const [folders, setFolders] = useState<string[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isRoot, setIsRoot] = useState(false);
    const [parentPath, setParentPath] = useState<string | null>(null);

    const fetchFolders = async (path: string) => {
        setLoading(true);
        setError(null);
        try {
            const res = await axios.get<FolderListResponse>(`http://localhost:8001/api/monitor/fs/list`, {
                params: { path: path }
            });
            setCurrentPath(res.data.current_path);
            setFolders(res.data.folders);
            setIsRoot(res.data.is_root);
            setParentPath(res.data.parent_path);
        } catch (err: any) {
            console.error(err);
            setError(err.response?.data?.detail || "폴더 목록을 불러오는데 실패했습니다.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            // If we have an initial path, try to load it, otherwise load root
            fetchFolders(currentPath);
        }
    }, [isOpen]);

    const handleFolderClick = (folderName: string) => {
        // If isRoot (Windows drives), the folderName is like "C:\"
        // If not root, folderName is just name, we need to join
        let newPath;
        if (isRoot) {
            newPath = folderName;
        } else {
            // Windows path joining (naive but works for now as backend handles separator mostly)
            // Actually backend returns name, we should join with separator.
            // On frontend we can't easily validly join paths cross-platform without knowing separator.
            // But we know this is likely Windows context from user.
            // However, a safer bet is to let backend handle joining? 
            // The backend list API only returns names. 
            // We'll assume Windows logic if backslashes present, else forward slashes.
            const sep = currentPath.includes('\\') ? '\\' : '/';
            // Handle root slash case
            const prefix = currentPath.endsWith(sep) ? currentPath : currentPath + sep;
            newPath = prefix + folderName;
        }
        fetchFolders(newPath);
    };

    const handleUp = () => {
        if (parentPath !== null) {
            fetchFolders(parentPath);
        }
    };

    const handleSelectCurrent = () => {
        onSelect(currentPath);
        onClose();
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-[100] flex items-center justify-center p-4 animate-in fade-in duration-200">
            <div className="bg-white rounded-2xl border border-slate-200 w-full max-w-lg shadow-2xl flex flex-col max-h-[80vh] animate-in zoom-in-95 duration-200">
                {/* Header */}
                <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50 rounded-t-2xl">
                    <h3 className="font-bold text-slate-800 flex items-center gap-2">
                        <FolderOpen size={20} className="text-indigo-600" />
                        폴더 선택
                    </h3>
                    <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
                        <X size={18} className="text-slate-500" />
                    </button>
                </div>

                {/* Path Bar */}
                <div className="px-6 py-3 bg-white border-b border-slate-100 flex items-center gap-2 shadow-sm z-10">
                    <button
                        onClick={handleUp}
                        disabled={!parentPath && !isRoot}
                        className="p-2 hover:bg-slate-100 rounded-lg text-slate-600 disabled:text-slate-300 disabled:cursor-not-allowed transition-colors"
                        title="상위 폴더"
                    >
                        <CornerLeftUp size={18} />
                    </button>
                    <div className="flex-1 overflow-hidden">
                        <div className="text-sm font-mono text-slate-600 bg-slate-100 px-3 py-1.5 rounded-lg truncate border border-slate-200" title={currentPath || "Computer"}>
                            {currentPath || "내 컴퓨터"}
                        </div>
                    </div>
                </div>

                {/* Folder List */}
                <div className="flex-1 overflow-y-auto p-2 custom-scrollbar min-h-[300px]">
                    {loading ? (
                        <div className="flex items-center justify-center h-full text-slate-400 gap-2">
                            <Loader2 className="animate-spin" size={24} />
                            <span className="text-sm">로딩 중...</span>
                        </div>
                    ) : error ? (
                        <div className="flex flex-col items-center justify-center h-full text-rose-500 gap-2 px-6 text-center">
                            <X size={24} />
                            <span className="text-sm font-medium">{error}</span>
                            <button onClick={() => fetchFolders(currentPath)} className="text-xs underline mt-2 hover:text-rose-700">다시 시도</button>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 gap-1">
                            {folders.length === 0 ? (
                                <div className="text-center py-10 text-slate-400 text-sm">
                                    폴더가 없습니다.
                                </div>
                            ) : (
                                folders.map((folder) => (
                                    <button
                                        key={folder}
                                        onClick={() => handleFolderClick(folder)}
                                        className="flex items-center gap-3 w-full px-4 py-3 hover:bg-indigo-50 text-left rounded-xl transition-colors group"
                                    >
                                        {isRoot ? (
                                            <HardDrive size={18} className="text-slate-400 group-hover:text-indigo-500" />
                                        ) : (
                                            <Folder size={18} className="text-amber-400 group-hover:text-amber-500" />
                                        )}
                                        <span className="text-sm text-slate-700 font-medium truncate group-hover:text-indigo-700">
                                            {folder}
                                        </span>
                                    </button>
                                ))
                            )}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3 bg-slate-50/50 rounded-b-2xl">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
                    >
                        취소
                    </button>
                    <button
                        onClick={handleSelectCurrent}
                        disabled={!currentPath || isRoot}
                        className="flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold rounded-xl shadow-lg shadow-indigo-200 transition-all disabled:opacity-50 disabled:shadow-none"
                    >
                        <Check size={16} />
                        이 폴더 선택
                    </button>
                </div>
            </div>
        </div>
    );
};
