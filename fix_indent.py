import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
normalized = []

for line in lines:
    if not line or not line[0].isspace():
        normalized.append(line)
    else:
        stripped = line.lstrip()
        indent_len = len(line) - len(stripped)
        new_indent = (indent_len // 5) * 4
        if indent_len % 5 > 0:
            new_indent += 4
        normalized.append(' ' * new_indent + stripped)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(normalized))

print('Indentation normalized to 4 spaces')
