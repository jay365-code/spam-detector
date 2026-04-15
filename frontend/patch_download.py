import sys

def refactor():
    with open('src/App.tsx', 'r', encoding='utf-8') as f:
        content = f.read()

    old_logic = """  const handleExcelSaveAs = async () => {
    if (!downloadUrl || !downloadFilename) return;

    try {
      // 항상 엑셀 분석 결과의 원본 파일네이밍(downloadFilename)을 우선 사용합니다.
      const suggestedExcelName = downloadFilename;

      // UI에 저장된 전체 JSON 상태를 백엔드로 보내 백지에서 완성본 엑셀 생성 (Regenerate)
      const response = await fetch('http://localhost:8000/api/excel/regenerate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: suggestedExcelName,
          is_trap: isTrapRunning,
          logs: logs
        })
      });
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
  };"""

    new_logic = """  const handleExcelSaveAs = async () => {
    if (!downloadUrl || !downloadFilename) return;

    try {
      // 항상 엑셀 분석 결과의 원본 파일네이밍(downloadFilename)을 우선 사용합니다.
      const suggestedExcelName = downloadFilename;
      let fileHandle = null;

      // 1. Open Save File Picker FIRST 
      // (This must happen immediately after click to satisfy browser security before network await)
      if ('showSaveFilePicker' in window) {
        // @ts-ignore
        fileHandle = await window.showSaveFilePicker({
          suggestedName: suggestedExcelName,
          types: [{
            description: 'Excel File',
            accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] },
          }],
        });
      }

      // 2. UI에 저장된 전체 JSON 상태를 백엔드로 보내 백지에서 완성본 엑셀 생성 (Regenerate)
      alert("백엔드에서 최신 데이터(JSON)를 바탕으로 엑셀을 재생성 중입니다... 잠시만 기다려주세요.");
      const response = await fetch('http://localhost:8000/api/excel/regenerate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: suggestedExcelName,
          is_trap: isTrapRunning,
          logs: logs
        })
      });
      
      if (!response.ok) {
        throw new Error(`서버 응답 오류: ${response.status}`);
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
          ? activeReportFileName.replace(/\\.json$/i, ".xlsx")
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
    }
  };"""
    
    if old_logic in content:
        content = content.replace(old_logic, new_logic)
        with open('src/App.tsx', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Patched handleExcelSaveAs successfully.")
    else:
        print("Could not find old handleExcelSaveAs in App.tsx")

if __name__ == '__main__':
    refactor()
