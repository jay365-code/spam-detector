import sys

def refactor():
    with open('src/App.tsx', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add state
    if "const [isRegeneratingExcel, setIsRegeneratingExcel]" not in content:
        state_anchor = "const [isProcessing, setIsProcessing] = useState(false);"
        new_state = state_anchor + "\n  const [isRegeneratingExcel, setIsRegeneratingExcel] = useState(false);"
        content = content.replace(state_anchor, new_state)

    # 2. Update handleExcelSaveAs
    old_download = """      // 2. UI에 저장된 전체 JSON 상태를 백엔드로 보내 백지에서 완성본 엑셀 생성 (Regenerate)
      alert("백엔드에서 최신 데이터(JSON)를 바탕으로 엑셀을 재생성 중입니다... 잠시만 기다려주세요.");
      const response = await fetch('http://localhost:8000/api/excel/regenerate', {"""
      
    new_download = """      // 2. UI에 저장된 전체 JSON 상태를 백엔드로 보내 백지에서 완성본 엑셀 생성 (Regenerate)
      setIsRegeneratingExcel(true);
      const response = await fetch('http://localhost:8000/api/excel/regenerate', {"""
    
    content = content.replace(old_download, new_download)
    
    # 3. Update catch and finally block
    old_catch = """    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        console.error('Excel Save As failed:', err);
        alert(`엑셀 재생성 및 다운로드 실패: ${(err as Error).message}`);
      }
    }
  };"""
    
    new_catch = """    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        console.error('Excel Save As failed:', err);
        alert(`엑셀 재생성 및 다운로드 실패: ${(err as Error).message}`);
      }
    } finally {
      setIsRegeneratingExcel(false);
    }
  };"""
  
    content = content.replace(old_catch, new_catch)
    
    # 4. Add Overlay Component at the very end before "</div>" of App
    overlay = """
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
    </div>
  );
}"""

    if "엑셀 재생성 오버레이" not in content:
        # Find the last "</div>\n  );\n}"
        idx = content.rfind("    </div>\n  );\n}")
        if idx != -1:
            content = content[:idx] + overlay
            # If there's an extra trailing, that's fine.
            
    with open('src/App.tsx', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Patched completely!")

if __name__ == '__main__':
    refactor()
