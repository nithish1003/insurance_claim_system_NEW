import re

with open(r'd:\insurance_claim_system_NEW\claims\templates\claims\claim_detail.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove comments
content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)

open_divs = len(re.findall(r'<div', content))
close_divs = len(re.findall(r'</div', content))

print(f"Open: {open_divs}, Close: {close_divs}, Diff: {open_divs - close_divs}")
