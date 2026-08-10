import os

file_path = r'd:\insurance_claim_system_NEW\policy\templates\policy\admin_policies.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace Table Headers and Row Loop
old_table_body = """                {% for policy in policies %}
                <tr>
                    <td class="ps-4 fw-bold text-white">{{ policy.policy.policy_number }}</td>
                    <td><span class="badge bg-secondary opacity-75">{{ policy.policy.policy_type|default:"General" }}</span></td>
                    <td><span class="text-muted px-2 py-1 rounded small" style="background: rgba(255,255,255,0.03);">{{ policy.policy.insurer_name|default:"-" }}</span></td>
                    <td class="fw-bold">₹{{ policy.policy.sum_insured|default:0|floatformat:0|intcomma }}</td>
                    <td class="text-info fw-bold">
                        {{ policy.policy.admin_premium_percent|default:0 }}% 
                        <span class="x-small text-muted d-block" style="font-size: 10px;">(₹{{ policy.final_premium|default:policy.policy.calculate_final_premium|floatformat:2|intcomma }})</span>
                    </td>
                    <td class="small text-muted">{{ policy.end_date|default:policy.policy.end_date|date:"M d, Y" }}</td>
                    <td>
                        <span class="badge {% if policy.status == 'active' %}active{% elif policy.status == 'approved' and not policy.is_paid %}awaiting-payment{% elif policy.status == 'rejected' %}rejected{% elif policy.status == 'pending' %}pending{% elif policy.status == 'expired' %}expired{% else %}default{% endif %}">
                            {% if policy.status == 'approved' and not policy.is_paid %}
                                Approved (Awaiting Payment)
                            {% else %}
                                {{ policy.get_status_display }}
                            {% endif %}
                        </span>
                    </td>
                    <td class="pe-4 text-end">
                        <div class="d-flex justify-content-end gap-2">
                            <a href="{% url 'policy:detail' policy.policy.public_id %}" class="btn-premium-sm hover-scale" title="View Details">
                                <i class="bi bi-eye"></i>
                            </a>
                            {% if policy.status == 'pending' %}
                            <a href="{% url 'policy:admin_review' policy.public_id %}" class="btn-premium-sm hover-scale" style="background: #f59e0b;" title="Review Application">
                                <i class="bi bi-clipboard-check"></i>
                            </a>
                            {% else %}
                            <a href="{% url 'policy:edit' policy.policy.public_id %}" class="btn-premium-sm hover-scale" style="background: rgba(255,255,255,0.1); color: white !important;" title="Edit Policy">
                                <i class="bi bi-pencil"></i>
                            </a>
                            {% endif %}
                        </div>
                    </td>
                </tr>"""

new_table_body = """                {% for policy in policies %}
                <tr>
                    <td class="ps-4 fw-bold text-white">{{ policy.policy_number }}</td>
                    <td><span class="badge bg-secondary opacity-75">{{ policy.policy_type|default:"General" }}</span></td>
                    <td><span class="text-muted px-2 py-1 rounded small" style="background: rgba(255,255,255,0.03);">{{ policy.insurer_name|default:"-" }}</span></td>
                    <td class="fw-bold">₹{{ policy.sum_insured|default:0|floatformat:0|intcomma }}</td>
                    <td class="text-info fw-bold">
                        {{ policy.admin_premium_percent|default:0 }}% 
                        <span class="x-small text-muted d-block" style="font-size: 10px;">(₹{{ policy.calculate_final_premium|floatformat:2|intcomma }})</span>
                    </td>
                    <td class="small text-muted">{{ policy.end_date|date:"M d, Y" }}</td>
                    <td>
                        <span class="badge {% if policy.status == 'active' %}active{% elif policy.status == 'pending' %}pending{% elif policy.status == 'expired' %}expired{% else %}default{% endif %}">
                            {{ policy.get_status_display }}
                        </span>
                    </td>
                    <td class="pe-4 text-end">
                        <div class="d-flex justify-content-end gap-2">
                            <a href="{% url 'policy:detail' policy.public_id %}" class="btn-premium-sm hover-scale" title="View Details">
                                <i class="bi bi-eye"></i>
                            </a>
                            <a href="{% url 'policy:edit' policy.public_id %}" class="btn-premium-sm hover-scale" style="background: rgba(255,255,255,0.1); color: white !important;" title="Edit Policy">
                                <i class="bi bi-pencil"></i>
                            </a>
                        </div>
                    </td>
                </tr>"""

if old_table_body in content:
    content = content.replace(old_table_body, new_table_body)
    print("Replaced Table Body in admin_policies.html")
else:
    print("Could not find table body in admin_policies.html")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
