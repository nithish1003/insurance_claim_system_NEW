(function () {
    function ready(fn) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", fn);
            return;
        }
        fn();
    }

    ready(function () {
        const body = document.body;
        const verdictForm = document.getElementById("verdictForm");
        const verdictActionInput = document.getElementById("reviewVerdictAction");
        const deleteClaimForm = document.getElementById("deleteClaimForm");
        const docModal = document.getElementById("docPreviewModal");
        const docPreviewBody = document.getElementById("docPreviewBody");
        const docPreviewTitle = document.getElementById("docPreviewTitle");
        const docPreviewOpen = document.getElementById("docPreviewOpen");

        let activeModal = null;

        function openModal(modalId) {
            const modal = document.getElementById(modalId);
            if (!modal) {
                return;
            }

            modal.hidden = false;
            body.style.overflow = "hidden";
            activeModal = modal;
        }

        function closeModal(modalId) {
            const modal = modalId ? document.getElementById(modalId) : activeModal;
            if (!modal) {
                return;
            }

            modal.hidden = true;
            if (modal === docModal && docPreviewBody) {
                docPreviewBody.replaceChildren();
            }

            if (activeModal === modal) {
                activeModal = null;
            }

            body.style.overflow = "";
        }

        async function confirmAction(title, text, confirmText, destructive) {
            if (window.InsureAlert) {
                const dialog = destructive ? window.InsureAlert.destructive : window.InsureAlert.confirm;
                return dialog(title, text, confirmText);
            }

            // High-fidelity fallback if InsureAlert is somehow missing
            if (window.Swal) {
                return window.Swal.fire({
                    title: title,
                    text: text,
                    icon: destructive ? 'warning' : 'question',
                    showCancelButton: true,
                    confirmButtonText: confirmText
                });
            }

            return Promise.resolve({ isConfirmed: window.confirm(text) });
        }

        function buildPreviewNode(url, type, name) {
            if (type === "pdf") {
                const frame = document.createElement("iframe");
                frame.className = "modal-preview-frame";
                frame.src = url;
                frame.title = name;
                return frame;
            }

            const image = document.createElement("img");
            image.className = "modal-preview-image";
            image.src = url;
            image.alt = name;
            image.addEventListener("error", function () {
                const fallback = document.createElement("div");
                fallback.className = "modal-preview-empty";
                fallback.innerHTML = "<i class=\"bi bi-exclamation-triangle\"></i><p>Preview unavailable for this file.</p>";
                docPreviewBody.replaceChildren(fallback);
            });
            return image;
        }

        document.querySelectorAll("[data-open-modal]").forEach(function (button) {
            button.addEventListener("click", function () {
                openModal(button.getAttribute("data-open-modal"));
            });
        });

        document.querySelectorAll("[data-close-modal]").forEach(function (button) {
            button.addEventListener("click", function () {
                closeModal(button.getAttribute("data-close-modal"));
            });
        });

        document.querySelectorAll(".doc-preview-btn").forEach(function (button) {
            button.addEventListener("click", function () {
                const url = button.getAttribute("data-doc-url");
                const type = button.getAttribute("data-doc-type");
                const name = button.getAttribute("data-doc-name") || "Supporting Document";

                if (!url || !docModal || !docPreviewBody || !docPreviewTitle || !docPreviewOpen) {
                    return;
                }

                docPreviewTitle.textContent = name;
                docPreviewOpen.href = url;
                docPreviewBody.replaceChildren(buildPreviewNode(url, type, name));
                openModal("docPreviewModal");
            });
        });

        document.querySelectorAll("[data-review-action]").forEach(function (button) {
            button.addEventListener("click", async function () {
                if (!verdictForm || !verdictActionInput) {
                    return;
                }

                const action = button.getAttribute("data-review-action");
                const isApprove = action === "approve";
                const result = await confirmAction(
                    isApprove ? "Approve Claim" : "Reject Claim",
                    isApprove
                        ? "Approve this claim and advance it into the settlement path?"
                        : "Reject this claim and record the decision in the audit trail?",
                    isApprove ? "Approve" : "Reject",
                    !isApprove
                );

                if (result && result.isConfirmed) {
                    verdictActionInput.value = action;
                    verdictForm.submit();
                }
            });
        });

        const deleteClaimButton = document.querySelector("[data-delete-claim]");
        if (deleteClaimButton && deleteClaimForm) {
            deleteClaimButton.addEventListener("click", async function () {
                const result = await confirmAction(
                    "Delete Claim",
                    "Permanently delete this claim and its review surface?",
                    "Delete Claim",
                    true
                );

                if (result && result.isConfirmed) {
                    deleteClaimForm.submit();
                }
            });
        }

        document.querySelectorAll("[data-delete-note]").forEach(function (link) {
            link.addEventListener("click", async function (event) {
                event.preventDefault();
                const result = await confirmAction(
                    "Delete Note",
                    "Remove this note from the audit discussion?",
                    "Delete Note",
                    true
                );

                if (result && result.isConfirmed) {
                    window.location.href = link.href;
                }
            });
        });

        const downloadPdfButton = document.querySelector("[data-download-pdf]");
        if (downloadPdfButton) {
            downloadPdfButton.addEventListener("click", function () {
                window.print();
            });
        }

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                closeModal();
            }
        });

    });
})();
