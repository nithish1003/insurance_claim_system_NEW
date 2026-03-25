import os

filepath = r'd:\insurance_claim_system_NEW\accounts\templates\accounts\dashboard_admin.html'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip_count = 0
skip_next_tr = False
skip_claim_type = False

for i, line in enumerate(lines):
    if skip_count > 0:
        skip_count -= 1
        continue
    
    if skip_next_tr:
        if '<tr>' in line:
            skip_next_tr = False
            continue
    
    if skip_claim_type:
        if '<td' in line and 'get_claim_type_display' in line:
            skip_claim_type = False
            continue
            
    # Search for the header of the Recent Claims table
    if '<th>Claim No</th>' in line and i > 600:
        new_lines.append(line) # Claim No
        new_lines.append(lines[i+1]) # Policyholder
        new_lines.append('                                <th class="text-center">Priority</th>\n')
        new_lines.append('                                <th>Reason</th>\n')
        skip_count = 2 # Skip Policy Number and Claim Type (664 and 665)
        continue
    
    if '{% for claim in recent_claims %}' in line:
        new_lines.append(line)
        # Add the highlighted row logic
        new_lines.append('                            <tr {% if forloop.counter <= 3 and claim.priority_level == "HIGH" %}style="background: rgba(239, 68, 68, 0.05); border-left: 3px solid #ef4444;"{% endif %}>\n')
        skip_next_tr = True
        continue
        
    # Update columns in the row
    if '<td class="text-id fw-bold">{{ claim.claim_number }}</td>' in line:
        new_lines.append('                                <td class="text-id fw-bold">\n')
        new_lines.append('                                    {{ claim.claim_number }}\n')
        new_lines.append('                                    {% if claim.emergency_flag %}<i class="bi bi-lightning-fill text-danger ms-1" title="Emergency"></i>{% endif %}\n')
        new_lines.append('                                </td>\n')
        continue

    if '<td class="text-id text-info-premium">{{ claim.policy.policy_number }}</td>' in line:
        # Replacement for Policy Number and Claim Type
        new_lines.append('                                <td class="text-center">\n')
        new_lines.append('                                    <span class="badge {% if claim.priority_level == "HIGH" %}bg-danger{% elif claim.priority_level == "MEDIUM" %}bg-warning text-dark{% else %}bg-secondary opacity-50{% endif %}" style="font-size: 0.62rem; min-width: 60px;">\n')
        new_lines.append('                                        {{ claim.priority_level|default:"LOW" }}\n')
        new_lines.append('                                    </span>\n')
        new_lines.append('                                </td>\n')
        new_lines.append('                                <td>\n')
        new_lines.append('                                    <div class="x-small text-muted text-wrap" style="max-width: 140px; line-height: 1.25;" title="{{ claim.priority_reason }}">\n')
        new_lines.append('                                        {{ claim.priority_reason|default:"-" }}\n')
        new_lines.append('                                    </div>\n')
        new_lines.append('                                </td>\n')
        skip_claim_type = True
        continue

    new_lines.append(line)

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("SUCCESS: Dashboard templates patched with prioritization layout.")
