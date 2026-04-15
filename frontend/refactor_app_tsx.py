import re
import sys

def refactor():
    with open('src/App.tsx', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update saveEdit
    # Find the saveEdit function
    # It starts at: const saveEdit = async () => { ... }
    
    old_saveEdit = """  const saveEdit = async () => {
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
          spam_probability: editingLog.spam_probability,
          is_trap: editingLog.is_trap || false,
          red_group: editingLog.red_group || false,
          added_urls: extractedUrls,
          added_signature: extractedSignature || null
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
  };"""

    new_saveEdit = """  const saveEdit = async () => {
    if (!editingLog) return;

    setEditSaving(true);
    try {
      // UI 상태만 즉각 업데이트 (백엔드는 엑셀 최종 저장 시 JSON 전체 기반으로 재생성)
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
              red_group: editingLog.red_group || false,
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
  };"""
    content = content.replace(old_saveEdit, new_saveEdit)
    
    # 2. Update handleExcelSaveAs
    # Find handleExcelSaveAs
    # Replace fetch logic
    
    old_saveAs_fetch = """      // 1. Fetch the file from server first (Include suggested name for header consistency)
      const fetchUrl = `${downloadUrl}${downloadUrl.includes('?') ? '&' : '?'}suggested_name=${encodeURIComponent(suggestedExcelName)}`;
      const response = await fetch(fetchUrl);"""
      
    new_saveAs_fetch = """      // UI에 저장된 전체 JSON 상태를 백엔드로 보내 백지에서 완성본 엑셀 생성 (Regenerate)
      const response = await fetch('http://localhost:8000/api/excel/regenerate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: suggestedExcelName,
          is_trap: isTrapRunning,
          logs: logs
        })
      });"""
    content = content.replace(old_saveAs_fetch, new_saveAs_fetch)

    with open('src/App.tsx', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    refactor()
