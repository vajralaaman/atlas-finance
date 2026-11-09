document.addEventListener('DOMContentLoaded', () => {
    // 1. Filter Drawer Toggle
    const filterToggle = document.getElementById('filter-toggle');
    const filterForm = document.getElementById('dashboard-filters');
    if (filterToggle && filterForm) {
        filterToggle.addEventListener('click', () => {
            const isHidden = filterForm.hasAttribute('hidden');
            if (isHidden) {
                filterForm.removeAttribute('hidden');
                filterToggle.setAttribute('aria-expanded', 'true');
            } else {
                filterForm.setAttribute('hidden', '');
                filterToggle.setAttribute('aria-expanded', 'false');
            }
        });
    }

    // 1.5 Export Dropdown Menu Toggle
    const exportBtn = document.getElementById('exportDropdownBtn');
    const exportMenu = document.getElementById('exportMenu');
    if (exportBtn && exportMenu) {
        exportBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isHidden = exportMenu.hasAttribute('hidden');
            if (isHidden) {
                exportMenu.removeAttribute('hidden');
                exportBtn.setAttribute('aria-expanded', 'true');
            } else {
                exportMenu.setAttribute('hidden', '');
                exportBtn.setAttribute('aria-expanded', 'false');
            }
        });
        document.addEventListener('click', (e) => {
            if (!exportMenu.contains(e.target) && e.target !== exportBtn) {
                exportMenu.setAttribute('hidden', '');
                exportBtn.setAttribute('aria-expanded', 'false');
            }
        });
    }

    // 2. Missing Data Alert Modal Controls
    const missingModal = document.getElementById('missingDataModal');
    const openMissingBtn = document.getElementById('openMissingModalBtn');
    const closeCrossBtn = document.getElementById('closeModalCross');
    const dismissModalBtn = document.getElementById('dismissModalBtn');

    function closeMissingModal() {
        if (missingModal) {
            missingModal.style.display = 'none';
        }
    }

    function openMissingModal() {
        if (missingModal) {
            missingModal.style.display = 'flex';
        }
    }

    if (closeCrossBtn) {
        closeCrossBtn.addEventListener('click', closeMissingModal);
    }
    if (dismissModalBtn) {
        dismissModalBtn.addEventListener('click', closeMissingModal);
    }
    if (openMissingBtn) {
        openMissingBtn.addEventListener('click', openMissingModal);
    }
    if (missingModal) {
        missingModal.addEventListener('click', (e) => {
            if (e.target === missingModal) {
                closeMissingModal();
            }
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && missingModal.style.display !== 'none') {
                closeMissingModal();
            }
        });
    }


    // 3. Charts Initialization
    const dataElement = document.getElementById('analytics-data');
    if (!dataElement || typeof Chart === 'undefined') return;

    let data = {};
    try {
        data = JSON.parse(dataElement.textContent);
    } catch (e) {
        console.error('Failed to parse analytics data', e);
        return;
    }

    function toggleEmptyMessage(canvasId, hasData) {
        const emptyMsg = document.querySelector(`.chart-empty[data-for="${canvasId}"]`);
        const canvas = document.getElementById(canvasId);
        if (emptyMsg) {
            emptyMsg.style.display = hasData ? 'none' : 'block';
        }
        if (canvas) {
            canvas.style.display = hasData ? 'block' : 'none';
        }
    }

    // Chart 1: Revenue vs Expenses (Monthly Bar Chart)
    const incomeExpenseCanvas = document.getElementById('incomeExpenseChart');
    const months = data.monthly_trends || [];
    const hasMonthlyData = months.length > 0;
    toggleEmptyMessage('incomeExpenseChart', hasMonthlyData);

    if (incomeExpenseCanvas && hasMonthlyData) {
        new Chart(incomeExpenseCanvas, {
            type: 'bar',
            data: {
                labels: months.map(item => item.month),
                datasets: [
                    {
                        label: 'Income',
                        data: months.map(item => item.income),
                        backgroundColor: '#16a34a',
                        borderRadius: 4
                    },
                    {
                        label: 'Expenses',
                        data: months.map(item => item.expenses),
                        backgroundColor: '#dc2626',
                        borderRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' }
                },
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });
    }

    // Chart 2: Invoice Status (Doughnut Chart)
    const invoiceCanvas = document.getElementById('invoiceChart');
    const hasInvoiceData = (data.invoice_count || 0) > 0;
    toggleEmptyMessage('invoiceChart', hasInvoiceData);

    if (invoiceCanvas && hasInvoiceData) {
        new Chart(invoiceCanvas, {
            type: 'doughnut',
            data: {
                labels: ['Paid', 'Pending'],
                datasets: [{
                    data: [data.paid_invoices || 0, data.pending_invoices || 0],
                    backgroundColor: ['#16a34a', '#f59e0b'],
                    borderWidth: 2,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' }
                }
            }
        });
    }

    // Chart 3: Expense Categories (Doughnut Chart)
    const categoryCanvas = document.getElementById('categoryChart');
    const categories = data.categories || [];
    const hasCategoryData = categories.length > 0;
    toggleEmptyMessage('categoryChart', hasCategoryData);

    if (categoryCanvas && hasCategoryData) {
        const palette = [
            '#2563eb', '#7c3aed', '#db2777', '#ea580c', '#059669',
            '#0891b2', '#4b5563', '#d97706', '#dc2626', '#65a30d'
        ];
        new Chart(categoryCanvas, {
            type: 'doughnut',
            data: {
                labels: categories.map(c => c.category),
                datasets: [{
                    data: categories.map(c => c.total),
                    backgroundColor: categories.map((_, i) => palette[i % palette.length]),
                    borderWidth: 2,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' }
                }
            }
        });
    }
});
