import os

file_path = r'd:\insurance_claim_system_NEW\accounts\templates\accounts\dashboard_admin.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace System Policies Section
old_policies_section = """    <!-- Policies Section -->
    <div id="section-policies" class="premium-table-card data-section mt-2">
        <div class="card-header d-flex justify-content-between">
            <h5><i class="bi bi-file-earmark-check-fill me-2 text-primary"></i>Policy Ledger</h5>
            <button class="btn btn-sm btn-link text-muted" onclick="this.closest('.data-section').style.display='none'"><i class="bi bi-x-lg"></i></button>
        </div>
        <div class="table-responsive">
            <table class="table system-policies-table">
                <thead><tr><th>Policy #</th><th>Type</th><th>Insurer</th><th>Sum Insured</th><th>Status</th></tr></thead>
                <tbody>
                    {% for p in policies %}
                    <tr>
                        <td class="text-id system-policy-number">{{ p.policy.policy_number }}</td>
                        <td>{{ p.policy.policy_type }}</td>
                        <td>{{ p.policy.insurer_name }}</td>
                        <td class="text-success-premium">₹{{ p.policy.sum_insured|intcomma }}</td>
                        <td><span class="policy-status-badge {{ p.admin_status_tone }}">{{ p.admin_status_label }}</span></td>
                    </tr>
                    {% empty %}
                    <tr><td colspan="5" class="text-center py-4">No policies found.</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>"""

new_policies_section = """    <!-- Policies Section: Master Inventory -->
    <div id="section-policies" class="premium-table-card data-section mt-2">
        <div class="card-header d-flex justify-content-between">
            <h5><i class="bi bi-building-fill-check me-2 text-primary"></i>System Policy Inventory</h5>
            <button class="btn btn-sm btn-link text-muted" onclick="this.closest('.data-section').style.display='none'"><i class="bi bi-x-lg"></i></button>
        </div>
        <div class="table-responsive">
            <table class="table system-policies-table">
                <thead><tr><th>Policy #</th><th>Type</th><th>Insurer</th><th>Sum Insured</th><th>Status</th></tr></thead>
                <tbody>
                    {% for p in all_policies %}
                    <tr>
                        <td class="text-id system-policy-number">{{ p.policy_number }}</td>
                        <td>{{ p.policy_type }}</td>
                        <td>{{ p.insurer_name }}</td>
                        <td class="text-success-premium">₹{{ p.sum_insured|intcomma }}</td>
                        <td>
                            <span class="policy-status-badge {% if p.status == 'active' %}status-active{% elif p.status == 'pending' %}status-pending{% else %}status-default{% endif %}">
                                {{ p.get_status_display }}
                            </span>
                        </td>
                    </tr>
                    {% empty %}
                    <tr><td colspan="5" class="text-center py-4">No master policies found.</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>"""

if old_policies_section in content:
    content = content.replace(old_policies_section, new_policies_section)
    print("Replaced System Policies Section")
else:
    print("Could not find System Policies Section exactly.")
    # Fallback to a partial match if possible
    if "id=\"section-policies\"" in content:
        print("Found section-policies via substring.")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
