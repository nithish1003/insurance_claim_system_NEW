filepath = r'd:\insurance_claim_system_NEW\accounts\templates\accounts\dashboard_staff.html'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip_next = 0

for i, line in enumerate(lines):
    if skip_next > 0:
        skip_next -= 1
        continue
        
    # Update Header
    if '<th>Claim Number</th>' in line and '<thead>' in lines[i-1]:
        new_lines.append(line)
        new_lines.append('                            <th>Urgency</th>\n')
        continue
        
    # Update Body Row
    if '<td class="fw-medium">' in line and '{{ claim.claim_number }}' in lines[i+1]:
        # Keep the Claim Number <td>
        new_lines.append(line)
        new_lines.append(lines[i+1])
        new_lines.append(lines[i+2])
        # Add Urgency <td>
        new_lines.append('                            <td>\n')
        new_lines.append('                                <span class="badge {% if claim.priority_level == "HIGH" %}bg-danger{% elif claim.priority_level == "MEDIUM" %}bg-warning text-dark{% else %}bg-secondary opacity-50{% endif %}" style="font-size: 10px; padding: 4px 10px;">\n')
        new_lines.append('                                    {{ claim.priority_level|default:"LOW" }}\n')
        new_lines.append('                                </span>\n')
        new_lines.append('                                <div class="x-small text-muted mt-1" style="font-size: 9px; max-width: 100px;">{{ claim.priority_reason|truncatechars:30 }}</div>\n')
        new_lines.append('                            </td>\n')
        skip_next = 2
        continue

    new_lines.append(line)

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("SUCCESS: Staff dashboard templates patched.")
