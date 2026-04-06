import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { MessageSquare, AlertTriangle, Check, X, User, Send, Square } from 'lucide-react';

interface ChatInterfaceProps {
    clientId: string;
    ws: WebSocket | null;
    hitlRequest: any | null;
    onHitlResponse: (decision: string, comment?: string) => void;
    onSendMessage: (message: string, mode: "TEXT" | "URL" | "Unified" | "IBSE") => void; // Updated prop
    onStopGeneration?: () => void; // New prop for stopping generation
    onClearChat?: () => void; // Optional prop to clear chat on parent
    isConnected: boolean; // New prop to track connection status
}

// ... imports
export const ChatInterface: React.FC<ChatInterfaceProps> = ({ ws, hitlRequest, onHitlResponse, onSendMessage, onStopGeneration, onClearChat, isConnected }) => {
    const [messages, setMessages] = useState<any[]>([]);
    const [inputText, setInputText] = useState('');
    const [hitlComment, setHitlComment] = useState('');
    const [isGenerating, setIsGenerating] = useState(false);
    const [isStopping, setIsStopping] = useState(false);

    useEffect(() => {
        if (!isGenerating) {
            setIsStopping(false);
        }
    }, [isGenerating]);
    const [mode, setMode] = useState<"TEXT" | "URL" | "Unified" | "IBSE">("Unified"); // Default to Unified
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Initial Greeting
    useEffect(() => {
        setMessages([{
            role: 'assistant',
            content: '분석할 메시지를 입력하세요.'
        }]);
    }, []);

    // Handle incoming WebSocket messages (Chat Response)
    useEffect(() => {
        if (!ws) return;

        const handleMessage = (event: MessageEvent) => {
            const data = JSON.parse(event.data);

            if (data.type === 'CHAT_RESPONSE') {
                setMessages(prev => [...prev, {
                    role: 'assistant',
                    content: data.content
                }]);
                setIsGenerating(false);
            } else if (data.type === 'CHAT_STREAM_START') {
                setMessages(prev => [...prev, {
                    role: 'assistant',
                    content: '',
                    isStreaming: true
                }]);
            } else if (data.type === 'CHAT_STREAM_CHUNK') {
                setMessages(prev => {
                    const lastMsg = prev[prev.length - 1];
                    if (lastMsg && lastMsg.role === 'assistant' && lastMsg.isStreaming) {
                        const newContent = lastMsg.content + data.content;
                        return [...prev.slice(0, -1), { ...lastMsg, content: newContent }];
                    }
                    return prev;
                });
            } else if (data.type === 'PROCESS_STATUS') {
                setMessages(prev => {
                    const lastMsg = prev[prev.length - 1];
                    if (lastMsg && lastMsg.role === 'assistant') {
                        const logs = lastMsg.processLogs || [];
                        return [...prev.slice(0, -1), { 
                            ...lastMsg, 
                            processStatus: data.content,
                            processLogs: [...logs, { time: new Date().toLocaleTimeString('en-GB', { hour12: false }), text: data.content }]
                        }];
                    }
                    return prev;
                });
            } else if (data.type === 'CHAT_STREAM_END') {
                setMessages(prev => {
                    const lastMsg = prev[prev.length - 1];
                    if (lastMsg && lastMsg.role === 'assistant') {
                        return [...prev.slice(0, -1), { ...lastMsg, isStreaming: false, processStatus: null }];
                    }
                    return prev;
                });
                setIsGenerating(false);
            }
        };

        ws.addEventListener('message', handleMessage);
        return () => ws.removeEventListener('message', handleMessage);
    }, [ws]);


    // Handle HITL Request
    useEffect(() => {
        if (hitlRequest) {
            setMessages(prev => [...prev, {
                role: 'assistant',
                type: 'HITL',
                content: 'AI가 확실하게 판단하기 어려워 사용자의 확인이 필요합니다.',
                data: hitlRequest
            }]);
        }
    }, [hitlRequest]);

    const handleDecision = (decision: string) => {
        onHitlResponse(decision, hitlComment);
        setMessages(prev => [...prev, {
            role: 'user',
            content: `${decision === 'SPAM' ? '스팸' : '정상'}으로 분류했습니다`,
            comment: hitlComment
        }]);
        setHitlComment('');
    };

    const handleSend = () => {
        if (!inputText.trim() || isGenerating) return;
        setMessages(prev => [...prev, { role: 'user', content: inputText }]);
        onSendMessage(inputText, mode);
        setInputText('');
        setIsGenerating(true);
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto'; // Reset height
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        setInputText(e.target.value);
        e.target.style.height = 'auto';
        e.target.style.height = `${Math.min(e.target.scrollHeight, 150)}px`;
    };

    const handleClearChat = () => {
        setMessages([{
            role: 'assistant',
            content: '채팅이 초기화되었습니다. 무엇을 도와드릴까요?'
        }]);
        if (onClearChat) {
            onClearChat();
        }
    };

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    return (
        <div className="flex flex-col h-full bg-transparent overflow-hidden w-full max-w-3xl mx-auto relative group-container">
            <style>{`
                @keyframes scan {
                    0% { top: -100%; opacity: 0; }
                    20% { opacity: 0.5; }
                    50% { opacity: 0.8; }
                    80% { opacity: 0.5; }
                    100% { top: 200%; opacity: 0; }
                }
                .scanning-effect::after {
                    content: '';
                    position: absolute;
                    left: 0;
                    right: 0;
                    height: 50%;
                    background: linear-gradient(to bottom, transparent, rgba(59, 130, 246, 0.5), transparent);
                    animation: scan 2s linear infinite;
                    pointer-events: none;
                }
            `}</style>

            <div className="absolute top-2 right-4 z-20 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                    onClick={handleClearChat}
                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-white bg-slate-800/80 px-2 py-1.5 rounded-full border border-slate-700 transition-colors"
                >
                    <MessageSquare className="w-3 h-3" /> 새 채팅
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-hide pt-10">
                {messages.map((msg, idx) => (
                    <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} w-full`}>
                        {msg.role === 'user' ? (
                            <div className="max-w-[80%] rounded-2xl p-4 bg-blue-600 text-white rounded-br-none">
                                <p className="whitespace-pre-wrap">{msg.content}</p>
                                {msg.comment && (
                                    <div className="mt-3 pt-3 border-t border-white/20 flex flex-col gap-1">
                                        <div className="flex items-center gap-1.5 text-xs font-bold text-blue-200">
                                            <User className="w-3 h-3" />
                                            <span>검수자 의견</span>
                                        </div>
                                        <div className="text-sm text-white/90 bg-black/20 p-2 rounded">
                                            {msg.comment}
                                        </div>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="w-full text-slate-200 leading-relaxed">
                                {msg.type === 'HITL' ? (
                                    <div className="max-w-[80%] rounded-2xl p-4 bg-slate-700 text-slate-200 rounded-bl-none">
                                        <div className="space-y-3">
                                            <div className="flex items-center gap-2 text-yellow-400 font-bold mb-1">
                                                <AlertTriangle className="w-5 h-5" />
                                                <span>판단 보류 (확인 필요)</span>
                                            </div>
                                            <p className="text-sm">{msg.content}</p>
                                            <div className="bg-black/30 p-3 rounded border border-slate-600 font-mono text-xs text-slate-300 break-all">
                                                {msg.data.message}
                                            </div>
                                            <div className="text-xs text-red-400 font-bold mb-2">
                                                스팸 확률: {Math.round(msg.data.spam_probability * 100)}%
                                            </div>
                                            <div className="text-xs text-slate-400">
                                                {msg.data.reason.replace(/^Reason:\s*/i, '').replace(/\(Prob:.*\)/, '')}
                                            </div>
                                            {hitlRequest === msg.data && (
                                                <div className="space-y-3 pt-2">
                                                    <textarea
                                                        value={hitlComment}
                                                        onChange={(e) => setHitlComment(e.target.value)}
                                                        placeholder="검수 의견을 입력하세요 (선택)"
                                                        className="w-full bg-slate-800/50 border border-slate-600 rounded p-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500 transition-colors resize-none"
                                                        rows={2}
                                                    />
                                                    <div className="flex gap-2">
                                                        <button
                                                            onClick={() => handleDecision('SPAM')}
                                                            className="flex-1 flex items-center justify-center gap-2 bg-red-500 hover:bg-red-600 text-white py-2 rounded-lg transition-colors"
                                                        >
                                                            <X className="w-4 h-4" /> 네, 스팸입니다
                                                        </button>
                                                        <button
                                                            onClick={() => handleDecision('HAM')}
                                                            className="flex-1 flex items-center justify-center gap-2 bg-green-500 hover:bg-green-600 text-white py-2 rounded-lg transition-colors"
                                                        >
                                                            <Check className="w-4 h-4" /> 아니요, 정상입니다
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ) : (
                                    <div className="flex items-start gap-3 animate-fade-in pl-1">
                                        <div className={`flex-shrink-0 w-8 h-8 rounded-full overflow-hidden border border-white/10 shadow-lg relative ${msg.isStreaming ? 'animate-bounce' : ''}`}>
                                            <img src="/icon.png" alt="AI Agent" className="w-full h-full object-cover" />
                                        </div>
                                        <div className="prose prose-invert prose-sm max-w-none w-full leading-relaxed break-words prose-p:my-0 prose-ul:my-2 prose-ul:ml-4 prose-ul:list-disc prose-li:my-0.5 prose-ol:my-2 prose-ol:ml-4 prose-ol:list-decimal prose-strong:text-blue-300 prose-strong:font-bold prose-headings:text-slate-100 prose-headings:font-bold prose-headings:mb-3 prose-headings:mt-4 prose-blockquote:border-l-4 prose-blockquote:border-slate-600 prose-blockquote:pl-4 prose-blockquote:italic prose-blockquote:text-slate-400 pt-1">
                                            {msg.processLogs && msg.processLogs.length > 0 && (
                                                <div className="mb-4 bg-slate-800/80 border border-slate-700 rounded-lg overflow-hidden flex flex-col font-mono text-[11px] w-full max-w-full">
                                                    <div className="bg-slate-800 px-3 py-1.5 border-b border-slate-700 flex items-center gap-2 text-slate-400">
                                                        <div className="flex gap-1.5">
                                                            <div className="w-2 h-2 rounded-full bg-red-400/80"></div>
                                                            <div className="w-2 h-2 rounded-full bg-yellow-400/80"></div>
                                                            <div className="w-2 h-2 rounded-full bg-green-400/80"></div>
                                                        </div>
                                                        <span className="ml-1 tracking-wider uppercase text-[9px] font-bold">Analysis Console</span>
                                                    </div>
                                                    <div className="px-3 py-2 space-y-1 max-h-[150px] overflow-y-auto scrollbar-hide flex flex-col">
                                                        {msg.processLogs.map((log: any, i: number) => (
                                                            <div key={i} className="flex gap-2 items-start opacity-90 hover:opacity-100 block whitespace-pre-wrap break-all break-words leading-relaxed font-sans text-xs">
                                                                <span className="text-slate-500 font-mono flex-shrink-0">[{log.time}]</span>
                                                                <span className={log.text.includes('⚠️') || log.text.includes('실패') || log.text.includes('재시도') ? 'text-amber-400 font-medium' : log.text.includes('✅') ? 'text-emerald-400' : 'text-blue-300'}>
                                                                    {log.text}
                                                                </span>
                                                            </div>
                                                        ))}
                                                        {msg.isStreaming && (
                                                            <div className="flex gap-2 items-start pt-1 font-sans text-xs">
                                                                <span className="text-blue-400 animate-pulse flex items-center mt-1.5"><div className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-ping" /></span>
                                                                <span className="text-slate-400 italic animate-pulse">Running...</span>
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            )}
                                            <div className="font-sans text-[15px]">
                                                <ReactMarkdown>{msg.content}</ReactMarkdown>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ))}
                {isGenerating && messages[messages.length - 1]?.role === 'user' && (
                    <div className="flex items-start gap-3 animate-fade-in pl-1">
                        <div className="flex-shrink-0 w-8 h-8 rounded-full overflow-hidden border border-white/10 shadow-lg relative animate-bounce">
                            <img src="/icon.png" alt="AI Agent" className="w-full h-full object-cover" />
                        </div>
                        <div className="prose prose-invert prose-sm max-w-none w-full">
                            <div className="font-sans text-[15px] italic text-slate-400 pt-1">
                                스팸 분석 중...
                            </div>
                        </div>
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* Mode Selection & Input Area */}
            <div className="p-4 bg-transparent pb-6 flex flex-col gap-2">

                <div className="relative flex items-end bg-slate-700/50 hover:bg-slate-700 transition-colors rounded-[24px] border-none focus-within:ring-2 focus-within:ring-blue-500/50">

                    {/* Mode Selector (Inside Input) - Vertically Centered */}
                    <div className="absolute left-3 top-1/2 -translate-y-1/2 z-10">
                        <div className="relative group">
                            <button
                                className={`flex items-center gap-1.5 px-3 py-2 rounded-full text-xs font-bold transition-all ${mode === "Unified" ? "bg-green-600/50 hover:bg-green-600 text-green-100" :
                                    mode === "URL" ? "bg-purple-600/50 hover:bg-purple-600 text-purple-100" :
                                        mode === "IBSE" ? "bg-orange-600/50 hover:bg-orange-600 text-orange-100" :
                                            "bg-slate-600/50 hover:bg-slate-600 text-slate-200"
                                    }`}
                            >
                                {mode === "TEXT" ? "Content 분석" : mode === "URL" ? "URL 분석" : mode === "IBSE" ? "시그니처 추출" : "✨ Smart 분석"}
                                <span className="text-[10px] opacity-70">▼</span>
                            </button>

                            {/* Dropdown Menu */}
                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-36 bg-slate-800 border border-slate-700 rounded-xl overflow-hidden shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all transform origin-bottom z-50">
                                <button
                                    onClick={() => setMode("Unified")}
                                    className={`w-full text-left px-4 py-3 text-sm hover:bg-slate-700 transition-colors ${mode === "Unified" ? "text-green-400 font-bold" : "text-slate-300"}`}
                                >
                                    ✨ Smart 분석
                                </button>
                                <button
                                    onClick={() => setMode("TEXT")}
                                    className={`w-full text-left px-4 py-3 text-sm hover:bg-slate-700 transition-colors ${mode === "TEXT" ? "text-blue-400 font-bold" : "text-slate-300"}`}
                                >
                                    Content 분석
                                </button>
                                <button
                                    onClick={() => setMode("URL")}
                                    className={`w-full text-left px-4 py-3 text-sm hover:bg-slate-700 transition-colors ${mode === "URL" ? "text-purple-400 font-bold" : "text-slate-300"}`}
                                >
                                    URL 분석
                                </button>
                                <button
                                    onClick={() => setMode("IBSE")}
                                    className={`w-full text-left px-4 py-3 text-sm hover:bg-slate-700 transition-colors ${mode === "IBSE" ? "text-orange-400 font-bold" : "text-slate-300"}`}
                                >
                                    시그니처 추출
                                </button>
                            </div>
                        </div>
                    </div>

                    <textarea
                        ref={textareaRef}
                        rows={1}
                        value={inputText}
                        onChange={handleInput}
                        onKeyDown={handleKeyDown}
                        disabled={isGenerating || !isConnected}
                        placeholder={
                            !isConnected
                                ? "서버와 연결이 끊어졌습니다. (재연결 시도 중...)"
                                : isGenerating
                                    ? "답변을 기다리는 중입니다..."
                                    : "이곳에 메시지를 입력하여 전문가와 상담하세요..."
                        }
                        className="w-full bg-transparent border-none rounded-[24px] py-4 pl-36 pr-12 text-slate-200 focus:outline-none resize-none overflow-hidden max-h-[150px] leading-relaxed placeholder-slate-500"
                        style={{ height: 'auto' }}
                    />
                    <button
                        onClick={() => {
                            if (isGenerating && onStopGeneration) {
                                setIsStopping(true);
                                onStopGeneration();
                            } else {
                                handleSend();
                            }
                        }}
                        className={`absolute right-2 bottom-2 p-2 rounded-full text-white transition-colors mb-1 mr-1 ${!isConnected
                            ? 'bg-slate-600 cursor-not-allowed text-slate-400'
                            : isGenerating
                                ? isStopping ? 'bg-slate-500 cursor-not-allowed text-slate-300' : 'bg-blue-500 hover:bg-blue-600 animate-pulse'
                                : !inputText.trim()
                                    ? 'bg-slate-600 cursor-not-allowed text-slate-400'
                                    : 'bg-blue-500 hover:bg-blue-600'
                            }`}
                        disabled={!isConnected || isStopping || (!isGenerating && !inputText.trim())}
                    >
                        {isGenerating ? <Square className="w-4 h-4 text-white" /> : <Send className="w-4 h-4 text-white" />}
                    </button>
                </div>
            </div>
        </div>
    );
};
