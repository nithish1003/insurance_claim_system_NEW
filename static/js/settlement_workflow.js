/**
 * ClaimIQ Settlement Workflow - Logic Engine
 * Handles payment execution, loading states, and success flow.
 */

document.addEventListener('DOMContentLoaded', function() {
    // --- INITIALIZE AOS ---
    if (window.AOS) {
        AOS.init({
            duration: 800,
            easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
            once: true
        });
    }

    const executeBtn = document.getElementById('executeSettlementBtn');
    const paymentForm = document.getElementById('settlementForm');
    const successOverlay = document.getElementById('successOverlay');
    const methodOptions = document.querySelectorAll('.method-option');
    const paymentModeInput = document.getElementById('paymentModeInput');
    
    // --- PAYMENT METHOD SELECTION ---
    methodOptions.forEach(option => {
        option.addEventListener('click', function() {
            methodOptions.forEach(opt => opt.classList.remove('selected'));
            this.classList.add('selected');
            const method = this.getAttribute('data-method');
            paymentModeInput.value = method;
        });
    });

    // --- EXECUTION FLOW ---
    if (executeBtn) {
        executeBtn.addEventListener('click', async function(e) {
            e.preventDefault();
            
            // 1. Confirm with SweetAlert if available
            if (window.Swal) {
                const result = await Swal.fire({
                    title: 'Authorize Payout?',
                    text: "You are about to execute a final banking-grade settlement payout. This action is irreversible.",
                    icon: 'warning',
                    showCancelButton: true,
                    confirmButtonColor: '#10b981',
                    cancelButtonColor: '#1e293b',
                    confirmButtonText: 'Yes, Execute Settlement',
                    background: '#0f172a',
                    color: '#fff',
                    customClass: {
                        popup: 'premium-swal-popup'
                    }
                });

                if (!result.isConfirmed) return;
            } else if (!confirm('Execute Settlement?')) {
                return;
            }

            // 2. Show Loading State
            executeBtn.disabled = true;
            executeBtn.innerHTML = `
                <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                <span>Authorizing with Gateway...</span>
            `;

            // 3. Simulate Transaction Delay (Banking Grade Simulation)
            setTimeout(() => {
                // Submit form via AJAX or standard POST
                // For this implementation, we'll do a standard POST to the backend
                // But first show the success overlay for the 'WOW' effect if we want
                // Actually, we should submit the form and the backend will redirect
                // However, the user wants a "Success Flow" on click.
                
                // Let's use fetch to submit and then show the success UI
                const formData = new FormData(paymentForm);
                
                fetch(paymentForm.action, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-CSRFToken': formData.get('csrfmiddlewaretoken')
                    }
                })
                .then(response => {
                    if (response.ok) {
                        showSuccessUI();
                    } else {
                        throw new Error('Settlement execution failed');
                    }
                })
                .catch(err => {
                    console.error(err);
                    executeBtn.disabled = false;
                    executeBtn.innerHTML = 'Execute Settlement';
                    if (window.Swal) {
                        Swal.fire('Error', 'Settlement failed. Please check gateway connectivity.', 'error');
                    }
                });
            }, 2000);
        });
    }

    function showSuccessUI() {
        // Generate a random transaction ID for display
        const txnId = 'TXN-' + Math.random().toString(36).substr(2, 9).toUpperCase();
        document.getElementById('displayTxnId').textContent = txnId;
        
        successOverlay.classList.add('active');
        
        // After showing success for a few seconds, redirect back to Admin Dashboard
        setTimeout(() => {
            window.location.href = '/accounts/admin-dashboard/';
        }, 5000);
    }
});
