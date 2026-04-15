def refactor():
    with open('src/App.tsx', 'r', encoding='utf-8') as f:
        content = f.read()

    old_logic = "red_group: editingLog.red_group || false,\n              spam_probability: editingLog.spam_probability"
    new_logic = "red_group: editingLog.red_group || false,\n              spam_probability: editingLog.spam_probability,\n              message_extracted_url: extractedUrls.join(', '),\n              ibse_signature: extractedSignature"
    if old_logic in content:
        content = content.replace(old_logic, new_logic)
        with open('src/App.tsx', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Patched saveEdit successfully.")
    else:
        print("Could not find old logic in App.tsx")

if __name__ == '__main__':
    refactor()
