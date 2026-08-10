import os

file_path = r'd:\insurance_claim_system_NEW\accounts\templates\accounts\dashboard_admin.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace Card 1
old_card = """        <!-- Card 1: Total Users -->
        <div class="status-card accent-blue" onclick="toggleSection('users', this)">
            <div class="card-icon-wrapper">
                <i class="bi bi-people"></i>
            </div>
            <div class="card-content-area">
                <div class="card-title">Total Users</div>
                <div class="card-value">{{ total_users }}</div>
                <div class="card-meta">Global user footprint</div>
            </div>
        </div>"""

new_card = """        <!-- Card 1: Identity & KYC (Requirement: Fix KYC Visibility) -->
        <div class="status-card accent-purple" onclick="toggleSection('users', this)">
            <div class="card-icon-wrapper">
                <i class="bi bi-shield-lock"></i>
            </div>
            <div class="card-content-area">
                <div class="card-title">Identity & KYC</div>
                <div class="card-value">{{ total_users }}</div>
                <div class="card-meta">
                    <span class="{% if total_kyc_pending > 0 %}text-warning{% else %}text-success{% endif %}">
                        {{ total_kyc_pending|default:0 }} Pending Verification
                    </span>
                </div>
            </div>
        </div>"""

if old_card in content:
    content = content.replace(old_card, new_card)
    print("Replaced Card 1")
else:
    # Try with different line endings if needed, but python 'r' usually handles it.
    # Let's try matching without leading spaces for robustness
    print("Could not find Old Card 1 exactly. Trying substring match...")
    if "Total Users" in content:
         print("Found 'Total Users' in content.")

# Replace Table Headers and Rows
old_table = """                <thead><tr><th>ID</th><th>Username</th><th>Email</th><th>Role</th><th>Joined</th></tr></thead>
                <tbody>
                    {% for u in users %}
                    <tr>
                        <td>#{{ u.id }}</td>
                        <td class="text-white fw-bold">{{ u.username }}</td>
                        <td>{{ u.email }}</td>
                        <td><span class="badge bg-secondary">{{ u.role }}</span></td>
                        <td>{{ u.date_joined|date:"M d, Y" }}</td>
                    </tr>"""

new_table = """                <thead><tr><th>ID</th><th>Username</th><th>Email</th><th>Role</th><th>KYC Status</th><th>Joined</th></tr></thead>
                <tbody>
                    {% for u in users %}
                    <tr>
                        <td>#{{ u.id }}</td>
                        <td class="text-white fw-bold">{{ u.username }}</td>
                        <td>{{ u.email }}</td>
                        <td><span class="badge bg-secondary">{{ u.role|upper }}</span></td>
                        <td>
                            {% if u.is_verified %}
                                <span class="badge-soft-success"><i class="bi bi-patch-check-fill me-1"></i>VERIFIED</span>
                            {% else %}
                                <span class="badge-soft-warning"><i class="bi bi-hourglass-split me-1"></i>PENDING</span>
                            {% endif %}
                        </td>
                        <td>{{ u.date_joined|date:"M d, Y" }}</td>
                    </tr>"""

if old_table in content:
    content = content.replace(old_table, new_table)
    print("Replaced Table")
else:
    print("Could not find Old Table exactly.")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
