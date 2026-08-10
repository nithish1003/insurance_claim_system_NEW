from django.urls import path
from . import views

app_name = "claim"

urlpatterns = [

    # Claim list
    path("", views.claim_list, name="list"),

    # Create claim
    path("create/", views.claim_submit, name="create"),

    # Claim detail
    path("<uuid:id>/", views.claim_detail, name="detail"),
    path("<uuid:id>/ai-audit/", views.ai_audit_api, name="ai_audit"),
    path("api/ai-audit/replay/", views.ai_audit_replay, name="ai_audit_replay"),
    path("api/ai-audit/verify/", views.verify_audit_signature, name="ai_audit_verify"),
    path("api/integrity/<uuid:id>/preview/", views.claim_integrity_api, name="claim_integrity_api"),
    path("test/", views.test_route, name="test_route"),
    path("<uuid:id>/intelligence/", views.claim_intelligence_api, name="intelligence_api"),

    # Edit claim
    path("edit/<uuid:id>/", views.claim_edit, name="edit"),

    # Delete claim
    path("delete/<uuid:id>/", views.claim_delete, name="delete"),

    # Review claim
    path("review/<uuid:id>/", views.claim_review, name="review"),
    path("staff/claim/<uuid:id>/review/", views.staff_claim_review, name="staff_review"),
    path("staff/claim/<uuid:id>/generate-remark/", views.generate_claim_remark_api, name="generate_remark"),
    path("api/auditor/review/", views.auditor_review_api, name="auditor_review_api"),

    # Update claim status
    path("status/<uuid:id>/", views.update_claim_status, name="update_status"),

    # Claim assessment
    path("assessment/<uuid:claim_id>/", views.claim_assessment, name="assessment"),

    # Claim settlement
    path("settlement/<uuid:claim_id>/", views.claim_settlement, name="settlement"),

    # Claim documents
    path("document/upload/<uuid:claim_id>/", views.upload_claim_document, name="upload_document"),
    path("document/delete/<uuid:id>/", views.delete_claim_document, name="delete_document"),
    path("document/view/<uuid:id>/", views.view_claim_document, name="view_document"),

    # Claim notes (Legacy API endpoints)
    path("note/add/<uuid:claim_id>/", views.add_claim_note, name="api_add_note"),
    path("note/delete/<int:note_id>/", views.delete_claim_note, name="api_delete_note"),

    # Claim history
    path("history/<uuid:claim_id>/", views.claim_history, name="history"),

    # Settlement Management
    path("admin/settlement-queue/", views.admin_settlement_queue, name="settlement_queue"),

    # Notes Management System
    path("notes/<uuid:claim_id>/", views.claim_notes_list, name="notes"),
    path("notes/add/<uuid:claim_id>/", views.add_claim_note, name="add_note"),
    path("notes/edit/<int:note_id>/", views.edit_claim_note, name="edit_note"),
    path("notes/delete/<int:note_id>/", views.delete_claim_note, name="delete_note"),
    path("notes/toggle-important/<int:note_id>/", views.mark_note_important, name="toggle_important"),
    path("notes/dashboard/", views.notes_dashboard, name="notes_dashboard"),
]
