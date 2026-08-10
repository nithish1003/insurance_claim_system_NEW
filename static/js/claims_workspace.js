/**
 * Claims Management Workspace - JS Interactions
 * Handles table interactions, real-time filtering, and row animations.
 */

document.addEventListener('DOMContentLoaded', () => {
    console.log("Claims Management Workspace initialized.");
    
    // Smooth scroll to row if needed
    const urlParams = new URLSearchParams(window.location.search);
    const highlightClaim = urlParams.get('highlight');
    if (highlightClaim) {
        const row = document.querySelector(`tr[data-claim-id="${highlightClaim}"]`);
        if (row) {
            row.classList.add('row-highlight');
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }
});

function quickFilter(status) {
    const rows = document.querySelectorAll('.workspace-table tbody tr');
    rows.forEach(row => {
        if (status === 'all' || row.dataset.status === status) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}
