import sys

def run():
    with open('src/App.tsx', 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = content.replace("is_trap: isTrapRunning,", "is_trap: logs.some(log => log?.is_trap) || false,")
    
    with open('src/App.tsx', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Fixed isTrapRunning bug!")

if __name__ == '__main__':
    run()
