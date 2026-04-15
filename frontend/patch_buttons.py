import re

def refactor():
    with open('src/App.tsx', 'r', encoding='utf-8') as f:
        content = f.read()

    # Mofidy HAM button
    old_ham_btn = "onClick={() => setEditingLog({ ...editingLog, is_spam: false, classification_code: '' })}"
    new_ham_btn = """onClick={() => {
                          const newReason = editingLog.reason ? `[수동 HAM 전환] ${editingLog.reason.replace(/\[수동 SPAM 전환\]\\s*/g, '')}` : '[수동 HAM 전환]';
                          setEditingLog({ ...editingLog, is_spam: false, classification_code: '', reason: newReason });
                        }}"""
    content = content.replace(old_ham_btn, new_ham_btn)

    # Modify SPAM button
    old_spam_btn = "onClick={() => setEditingLog({ ...editingLog, is_spam: true, classification_code: editingLog.classification_code || '1' })}"
    new_spam_btn = """onClick={() => {
                          const newReason = editingLog.reason ? `[수동 SPAM 전환] ${editingLog.reason.replace(/\[수동 HAM 전환\]\\s*/g, '')}` : '[수동 SPAM 전환]';
                          setEditingLog({ ...editingLog, is_spam: true, classification_code: editingLog.classification_code || '1', reason: newReason });
                        }}"""
    content = content.replace(old_spam_btn, new_spam_btn)

    # Modify Red Group button
    old_red_btn = "onClick={() => setEditingLog({ ...editingLog, red_group: !editingLog.red_group })}"
    new_red_btn = """onClick={() => {
                            const isTurningOn = !editingLog.red_group;
                            let newReason = editingLog.reason || '';
                            if (isTurningOn && !newReason.includes('[수동 Red Group 지정]')) {
                              newReason = `[수동 Red Group 지정] ${newReason}`;
                            } else if (!isTurningOn) {
                              newReason = newReason.replace(/\[수동 Red Group 지정\]\\s*/g, '');
                            }
                            setEditingLog({ ...editingLog, red_group: isTurningOn, reason: newReason });
                          }}"""
    content = content.replace(old_red_btn, new_red_btn)

    with open('src/App.tsx', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    refactor()
