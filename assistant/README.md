# 🤖 ClaimIQ AI Assistant

A modular Django application providing role-aware support across the insurance platform using a hybrid response engine.

## Core Request Flow
1. User opens floating assistant widget.
2. Frontend sends async request to `/assistant/api/chat/`.
3. Backend identifies session and user role.
4. Intent router selects the best response path.

## Response Layers
### 1. FAQ Engine
Fast predefined answers for common queries such as claim filing, renewal, KYC, and policy guidance. Implemented in `rule_engine.py`.

### 2. Personalized Data Layer
Authenticated users can retrieve their own claim status, premium due dates, active policy details, and renewal schedules. Powered by `db_service.py`.

### 3. Operations Copilot
Staff and admins can access operational summaries such as pending claims, KYC backlogs, and workload queues. Strictly guarded via role-based intent checks.

## Security Model
* **Guests**: Public FAQs and greetings only.
* **Customers**: Public FAQs + Personal Data (requires login).
* **Staff**: Operational workload summaries.
* **Admins**: Full platform analytics and fraud alerts.

## UI Layer
Modern floating chat widget with:
- Glassmorphism Orb Button
- Neural Breathing Pulse
- Typewriter Animation
- Role-Aware Quick Actions
- Dark Fintech Styling

## Key Documentation
- `services/router.py`: Central intent routing logic.
- `services/db_service.py`: Secure cross-app model queries.
- `services/rule_engine.py`: High-speed FAQ resolution.
- `static/assistant/chat.js`: Frontend asynchronous dialogue controller.
