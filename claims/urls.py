from django.urls import path
from . import views

app_name = "claim"

urlpatterns = [

    # Claim list
    path("", views.claim_list, name="list"),

    # Create claim
    path("create/", views.claim_submit, name="create"),

    # Claim detail
    path("<int:id>/", views.claim_detail, name="detail"),

    # Edit claim
    path("edit/<int:id>/", views.claim_edit, name="edit"),

    # Delete claim
    path("delete/<int:id>/", views.claim_delete, name="delete"),

    # Review claim
    path("review/<int:id>/", views.claim_review, name="review"),
    path("staff/claim/<int:id>/review/", views.staff_claim_review, name="staff_review"),

    # Update claim status
    path("status/<int:id>/", views.update_claim_status, name="update_status"),

    # Claim assessment
    path("assessment/<int:claim_id>/", views.claim_assessment, name="assessment"),

    # Claim settlement
    path("settlement/<int:claim_id>/", views.claim_settlement, name="settlement"),

    # Claim documents
    path("document/upload/<int:claim_id>/", views.upload_claim_document, name="upload_document"),
    path("document/delete/<int:id>/", views.delete_claim_document, name="delete_document"),
    path("document/view/<int:id>/", views.view_claim_document, name="view_document"),

    # Claim notes
    path("note/add/<int:claim_id>/", views.add_claim_note, name="add_note"),
    path("note/delete/<int:note_id>/", views.delete_claim_note, name="delete_note"),

    # Claim history
    path("history/<int:claim_id>/", views.claim_history, name="history"),

    # Notes Management System
    path("notes/<int:claim_id>/", views.claim_notes_list, name="notes"),
    path("notes/add/<int:claim_id>/", views.add_claim_note, name="add_note"),
    path("notes/edit/<int:note_id>/", views.edit_claim_note, name="edit_note"),
    path("notes/delete/<int:note_id>/", views.delete_claim_note, name="delete_note"),
    path("notes/toggle-important/<int:note_id>/", views.mark_note_important, name="toggle_important"),
    path("notes/dashboard/", views.notes_dashboard, name="notes_dashboard"),
]
