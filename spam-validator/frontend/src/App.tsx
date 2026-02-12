import { useState } from 'react';
import { BarChart3, CheckCircle2, LayoutDashboard } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import ValidatorPage from './pages/ValidatorPage';
import MonitorPage from './pages/MonitorPage';

// --- Utility ---
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'validator' | 'monitor'>('validator');

  return (
    <div className="min-h-screen bg-[#f8fafc] text-slate-900 font-sans pb-20">
      {/* Header & Navigation */}
      <nav className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between shadow-sm sticky top-0 z-20">
        <div className="flex items-center gap-10">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-indigo-600 rounded-xl flex items-center justify-center text-white shadow-lg shadow-indigo-200">
              <BarChart3 size={20} className="stroke-[2.5]" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-slate-900">Spam Validator</h1>
              <p className="text-xs text-slate-500 font-medium">Model Evaluation Tool</p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl">
            <button
              onClick={() => setActiveTab('validator')}
              className={cn(
                "px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition-all",
                activeTab === 'validator'
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-200/50"
              )}
            >
              <CheckCircle2 size={16} />
              Validator
            </button>
            <button
              onClick={() => setActiveTab('monitor')}
              className={cn(
                "px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition-all",
                activeTab === 'monitor'
                  ? "bg-white text-indigo-700 shadow-sm"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-200/50"
              )}
            >
              <LayoutDashboard size={16} />
              Monitor
            </button>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-xs font-semibold text-slate-400 bg-slate-100 px-3 py-1.5 rounded-full">v1.1.0</div>
        </div>
      </nav>

      {/* Page Content */}
      <div className={activeTab === 'validator' ? 'block' : 'hidden'}>
        <ValidatorPage />
      </div>
      <div className={activeTab === 'monitor' ? 'block' : 'hidden'}>
        <MonitorPage />
      </div>
    </div>
  );
}
