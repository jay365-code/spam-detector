with open('backend/tmp/diff_head.txt', encoding='utf-8') as f:
    lines = f.readlines()
with open('backend/tmp/diff_summary.txt', 'w', encoding='utf-8') as out:
    for line in lines:
        if (line.startswith('+') and not line.startswith('+++')) or (line.startswith('-') and not line.startswith('---')) or line.startswith('diff --git'):
            out.write(line)
