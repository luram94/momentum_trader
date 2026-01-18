/**
 * HQM Momentum Scanner - Frontend JavaScript
 * Now with database caching support!
 */

// State
let scanResults = null;
let allocationChart = null;
let hqmChart = null;
let statusPollInterval = null;
let hasData = false;

// DOM Elements
const scanForm = document.getElementById('scanForm');
const scanBtn = document.getElementById('scanBtn');
const scanHint = document.getElementById('scanHint');
const portfolioSizeInput = document.getElementById('portfolioSize');
const numPositionsInput = document.getElementById('numPositions');
const numPositionsDisplay = document.getElementById('numPositionsDisplay');
const positionSizeDisplay = document.getElementById('positionSize');
const positionWeightDisplay = document.getElementById('positionWeight');
const progressSection = document.getElementById('progressSection');
const progressBar = document.getElementById('progressBar');
const progressMessage = document.getElementById('progressMessage');
const emptyState = document.getElementById('emptyState');
const resultsTable = document.getElementById('resultsTable');
const resultsBody = document.getElementById('resultsBody');
const summaryCard = document.getElementById('summaryCard');
const chartsRow = document.getElementById('chartsRow');
const legendCard = document.getElementById('legendCard');
const exportBtn = document.getElementById('exportBtn');

// Refresh elements
const refreshBtn = document.getElementById('refreshBtn');
const refreshProgress = document.getElementById('refreshProgress');
const refreshProgressBar = document.getElementById('refreshProgressBar');
const refreshMessage = document.getElementById('refreshMessage');
const stockCountDisplay = document.getElementById('stockCount');
const dataAgeDisplay = document.getElementById('dataAge');
const lastRefreshDisplay = document.getElementById('lastRefresh');
const noDataAlert = document.getElementById('noDataAlert');

// SMA10 filter elements
const enableSma10Filter = document.getElementById('enableSma10Filter');
const sma10FilterControls = document.getElementById('sma10FilterControls');
const maxSma10DistanceInput = document.getElementById('maxSma10Distance');
const maxSma10Display = document.getElementById('maxSma10Display');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    updatePositionCalculations();
    fetchDataStatus();

    // Event listeners
    numPositionsInput.addEventListener('input', updatePositionCalculations);
    portfolioSizeInput.addEventListener('input', updatePositionCalculations);
    scanForm.addEventListener('submit', handleScanSubmit);
    refreshBtn.addEventListener('click', handleRefresh);
    exportBtn.addEventListener('click', exportToCSV);

    // SMA10 filter event listeners
    enableSma10Filter.addEventListener('change', toggleSma10Filter);
    maxSma10DistanceInput.addEventListener('input', updateSma10Display);

    // Poll data status periodically
    setInterval(fetchDataStatus, 60000); // Every minute
});

/**
 * Toggle SMA10 filter controls visibility
 */
function toggleSma10Filter() {
    if (enableSma10Filter.checked) {
        sma10FilterControls.classList.remove('d-none');
    } else {
        sma10FilterControls.classList.add('d-none');
    }
}

/**
 * Update SMA10 distance display
 */
function updateSma10Display() {
    const value = parseInt(maxSma10DistanceInput.value);
    maxSma10Display.textContent = `Max +${value}% over SMA10`;
}

/**
 * Fetch and display data status
 */
async function fetchDataStatus() {
    try {
        const response = await fetch('/api/data-status');
        const data = await response.json();

        hasData = data.has_data;

        // Update display
        stockCountDisplay.textContent = data.stock_count.toLocaleString();

        if (data.data_age_hours === null || data.data_age_hours === Infinity) {
            dataAgeDisplay.textContent = 'No data';
            dataAgeDisplay.className = 'fw-bold text-warning';
        } else if (data.data_age_hours < 1) {
            dataAgeDisplay.textContent = '< 1 hour';
            dataAgeDisplay.className = 'fw-bold text-success';
        } else if (data.data_age_hours < 4) {
            dataAgeDisplay.textContent = `${data.data_age_hours} hours`;
            dataAgeDisplay.className = 'fw-bold text-success';
        } else if (data.data_age_hours < 24) {
            dataAgeDisplay.textContent = `${data.data_age_hours} hours`;
            dataAgeDisplay.className = 'fw-bold text-warning';
        } else {
            const days = Math.floor(data.data_age_hours / 24);
            dataAgeDisplay.textContent = `${days} day${days > 1 ? 's' : ''}`;
            dataAgeDisplay.className = 'fw-bold text-danger';
        }

        if (data.last_refresh) {
            const date = new Date(data.last_refresh);
            lastRefreshDisplay.textContent = date.toLocaleString();
        } else {
            lastRefreshDisplay.textContent = 'Never';
        }

        // Show/hide no data alert
        if (!hasData) {
            noDataAlert.classList.remove('d-none');
            scanBtn.disabled = true;
            scanHint.textContent = 'Refresh data first to enable scanning';
            scanHint.classList.remove('d-none');
        } else {
            noDataAlert.classList.add('d-none');
            scanBtn.disabled = false;
            scanHint.classList.add('d-none');
        }

    } catch (error) {
        console.error('Failed to fetch data status:', error);
    }
}

/**
 * Handle data refresh
 */
async function handleRefresh() {
    try {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Refreshing...';
        refreshProgress.classList.remove('d-none');

        const response = await fetch('/api/refresh', { method: 'POST' });
        const data = await response.json();

        if (!data.success) {
            alert(data.error || 'Failed to start refresh');
            resetRefreshButton();
            return;
        }

        // Poll for progress
        startRefreshPolling();

    } catch (error) {
        console.error('Refresh error:', error);
        alert('Failed to start refresh. Please try again.');
        resetRefreshButton();
    }
}

/**
 * Start polling for refresh status
 */
function startRefreshPolling() {
    if (statusPollInterval) {
        clearInterval(statusPollInterval);
    }

    statusPollInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();

            refreshProgressBar.style.width = `${data.progress}%`;
            refreshMessage.textContent = data.message;

            if (data.status === 'completed' || data.status === 'idle') {
                clearInterval(statusPollInterval);
                resetRefreshButton();
                refreshProgress.classList.add('d-none');
                fetchDataStatus();
            } else if (data.status === 'error') {
                clearInterval(statusPollInterval);
                resetRefreshButton();
                alert('Refresh failed: ' + data.message);
            }

        } catch (error) {
            console.error('Status poll error:', error);
        }
    }, 500);
}

/**
 * Reset refresh button state
 */
function resetRefreshButton() {
    refreshBtn.disabled = false;
    refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i>Refresh';
}

/**
 * Update position size calculations
 */
function updatePositionCalculations() {
    const portfolioSize = parseFloat(portfolioSizeInput.value) || 10000;
    const numPositions = parseInt(numPositionsInput.value) || 8;

    const positionSize = portfolioSize / numPositions;
    const positionWeight = 100 / numPositions;

    numPositionsDisplay.textContent = `${numPositions} stocks`;
    positionSizeDisplay.textContent = `$${positionSize.toLocaleString('en-US', {maximumFractionDigits: 0})}`;
    positionWeightDisplay.textContent = `${positionWeight.toFixed(1)}%`;
}

/**
 * Handle scan form submission
 */
async function handleScanSubmit(e) {
    e.preventDefault();

    if (!hasData) {
        alert('Please refresh data first.');
        return;
    }

    const portfolioSize = parseFloat(portfolioSizeInput.value);
    const numPositions = parseInt(numPositionsInput.value);

    // Validate
    if (portfolioSize < 1000) {
        alert('Portfolio size must be at least $1,000');
        return;
    }

    // Get SMA10 filter setting
    const maxSma10Distance = enableSma10Filter.checked ? parseInt(maxSma10DistanceInput.value) : null;

    // Start scan
    try {
        const response = await fetch('/api/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                portfolio_size: portfolioSize,
                num_positions: numPositions,
                max_sma10_distance: maxSma10Distance
            })
        });

        const data = await response.json();

        if (!data.success) {
            alert(data.error || 'Failed to start scan');
            return;
        }

        // Show progress
        showProgress();
        startScanPolling();

    } catch (error) {
        console.error('Scan error:', error);
        alert('Failed to start scan. Please try again.');
    }
}

/**
 * Show progress section
 */
function showProgress() {
    scanBtn.classList.add('scanning');
    scanBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Scanning...';
    scanBtn.disabled = true;
    progressSection.classList.remove('d-none');
    progressBar.style.width = '0%';
}

/**
 * Hide progress section
 */
function hideProgress() {
    scanBtn.classList.remove('scanning');
    scanBtn.innerHTML = '<i class="bi bi-search me-2"></i>Run Scan';
    scanBtn.disabled = false;
    progressSection.classList.add('d-none');
}

/**
 * Start polling for scan status
 */
function startScanPolling() {
    if (statusPollInterval) {
        clearInterval(statusPollInterval);
    }

    statusPollInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();

            // Update progress
            progressBar.style.width = `${data.progress}%`;
            progressMessage.textContent = data.message;

            // Check if complete
            if (data.status === 'completed') {
                clearInterval(statusPollInterval);
                hideProgress();
                fetchResults();
            } else if (data.status === 'error') {
                clearInterval(statusPollInterval);
                hideProgress();
                alert('Scan failed: ' + data.message);
            }

        } catch (error) {
            console.error('Status poll error:', error);
        }
    }, 300);
}

/**
 * Fetch and display results
 */
async function fetchResults() {
    try {
        const response = await fetch('/api/results');
        const data = await response.json();

        if (!data.success) {
            alert(data.error || 'Failed to fetch results');
            return;
        }

        scanResults = data;
        displayResults(data.results, data.summary);

    } catch (error) {
        console.error('Fetch results error:', error);
        alert('Failed to fetch results. Please try again.');
    }
}

/**
 * Display scan results
 */
function displayResults(results, summary) {
    // Show/hide elements
    emptyState.classList.add('d-none');
    resultsTable.classList.remove('d-none');
    summaryCard.classList.remove('d-none');
    chartsRow.classList.remove('d-none');
    legendCard.classList.remove('d-none');
    exportBtn.classList.remove('d-none');

    // Update summary
    document.getElementById('summaryScanned').textContent = summary.total_scanned.toLocaleString();
    document.getElementById('summaryFiltered').textContent = summary.after_quality_filter.toLocaleString();
    document.getElementById('summaryInvested').textContent = `$${summary.total_invested.toLocaleString()}`;
    document.getElementById('summaryCash').textContent = `$${summary.cash_remaining.toLocaleString()}`;

    // Build table
    resultsBody.innerHTML = results.map((stock, index) => `
        <tr>
            <td class="text-muted">${index + 1}</td>
            <td class="ticker-cell">
                <a href="https://es.tradingview.com/chart/EyK3ZRHL/?symbol=${stock.Exchange}%3A${stock.Ticker}"
                   target="_blank"
                   class="ticker-link"
                   title="Ver gráfico en TradingView">
                    ${stock.Ticker}
                    <i class="bi bi-box-arrow-up-right ms-1 small"></i>
                </a>
                <span class="badge ${stock.Exchange === 'NASDAQ' ? 'bg-info' : 'bg-secondary'} exchange-badge">
                    ${stock.Exchange}
                </span>
            </td>
            <td>$${stock.Price.toFixed(2)}</td>
            <td>
                <span class="hqm-badge ${stock.HQM_Score >= 90 ? 'hqm-excellent' : 'hqm-good'}">
                    ${stock.HQM_Score}
                </span>
            </td>
            <td>${formatSma10Distance(stock.SMA10_Distance)}</td>
            <td>${formatReturn(stock.Return_1M, stock.Pct_1M)}</td>
            <td>${formatReturn(stock.Return_3M, stock.Pct_3M)}</td>
            <td>${formatReturn(stock.Return_6M, stock.Pct_6M)}</td>
            <td>${formatReturn(stock.Return_1Y, stock.Pct_1Y)}</td>
            <td class="fw-bold">${stock.Shares}</td>
            <td class="text-success">$${stock.Value.toLocaleString()}</td>
            <td>${stock.Weight.toFixed(1)}%</td>
        </tr>
    `).join('');

    // Update charts
    updateCharts(results);
}

/**
 * Format return value with percentile indicator
 */
function formatReturn(returnVal, percentile) {
    const pctClass = getPctClass(percentile);
    const returnClass = returnVal >= 0 ? 'return-positive' : 'return-negative';
    const sign = returnVal >= 0 ? '+' : '';

    return `
        <span class="pct-indicator ${pctClass}"></span>
        <span class="${returnClass}">${sign}${(returnVal * 100).toFixed(1)}%</span>
    `;
}

/**
 * Get CSS class for percentile
 */
function getPctClass(percentile) {
    if (percentile >= 75) return 'pct-high';
    if (percentile >= 50) return 'pct-medium';
    if (percentile >= 25) return 'pct-low';
    return 'pct-very-low';
}

/**
 * Format SMA10 distance with color coding
 * Green: close to SMA10 (good entry), Yellow: moderately extended, Red: very extended
 */
function formatSma10Distance(distance) {
    if (distance === null || distance === undefined) {
        return '<span class="text-muted">-</span>';
    }

    const sign = distance >= 0 ? '+' : '';
    let colorClass = 'sma10-good';      // Green: <= 5%
    let icon = 'bi-check-circle-fill';

    if (distance > 15) {
        colorClass = 'sma10-extended';   // Red: > 15%
        icon = 'bi-exclamation-triangle-fill';
    } else if (distance > 8) {
        colorClass = 'sma10-moderate';   // Yellow: 8-15%
        icon = 'bi-dash-circle-fill';
    }

    return `
        <span class="${colorClass}" title="Distance from 10-day moving average">
            <i class="bi ${icon} me-1 small"></i>${sign}${distance.toFixed(1)}%
        </span>
    `;
}

/**
 * Update charts with results
 */
function updateCharts(results) {
    const tickers = results.map(r => r.Ticker);
    const values = results.map(r => r.Value);
    const hqmScores = results.map(r => r.HQM_Score);

    // Colors
    const colors = [
        '#198754', '#20c997', '#0dcaf0', '#0d6efd',
        '#6610f2', '#6f42c1', '#d63384', '#dc3545',
        '#fd7e14', '#ffc107', '#28a745', '#17a2b8'
    ];

    // Destroy existing charts
    if (allocationChart) allocationChart.destroy();
    if (hqmChart) hqmChart.destroy();

    // Allocation Pie Chart
    const allocationCtx = document.getElementById('allocationChart').getContext('2d');
    allocationChart = new Chart(allocationCtx, {
        type: 'doughnut',
        data: {
            labels: tickers,
            datasets: [{
                data: values,
                backgroundColor: colors.slice(0, results.length),
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#adb5bd',
                        padding: 10,
                        font: { size: 11 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const value = context.raw;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = ((value / total) * 100).toFixed(1);
                            return `$${value.toLocaleString()} (${pct}%)`;
                        }
                    }
                }
            }
        }
    });

    // HQM Score Bar Chart
    const hqmCtx = document.getElementById('hqmChart').getContext('2d');
    hqmChart = new Chart(hqmCtx, {
        type: 'bar',
        data: {
            labels: tickers,
            datasets: [{
                label: 'HQM Score',
                data: hqmScores,
                backgroundColor: hqmScores.map(score =>
                    score >= 95 ? '#198754' :
                    score >= 90 ? '#20c997' :
                    score >= 85 ? '#0dcaf0' : '#0d6efd'
                ),
                borderWidth: 0,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            scales: {
                x: {
                    min: 80,
                    max: 100,
                    grid: { color: 'rgba(255,255,255,0.1)' },
                    ticks: { color: '#adb5bd' }
                },
                y: {
                    grid: { display: false },
                    ticks: { color: '#adb5bd', font: { weight: 'bold' } }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => `HQM Score: ${context.raw}`
                    }
                }
            }
        }
    });
}

/**
 * Export results to CSV
 */
function exportToCSV() {
    if (!scanResults || !scanResults.results) {
        alert('No results to export');
        return;
    }

    const headers = [
        'Ticker', 'Price', 'Market Cap', 'Exchange',
        'SMA10 Distance', 'HQM Score',
        '1M Return', '1M Pct', '3M Return', '3M Pct',
        '6M Return', '6M Pct', '1Y Return', '1Y Pct',
        'Shares', 'Value', 'Weight'
    ];

    const rows = scanResults.results.map(r => [
        r.Ticker,
        r.Price,
        r.Market_Cap_Display,
        r.Exchange,
        r.SMA10_Distance !== null ? r.SMA10_Distance.toFixed(1) + '%' : '-',
        r.HQM_Score,
        (r.Return_1M * 100).toFixed(2) + '%',
        r.Pct_1M,
        (r.Return_3M * 100).toFixed(2) + '%',
        r.Pct_3M,
        (r.Return_6M * 100).toFixed(2) + '%',
        r.Pct_6M,
        (r.Return_1Y * 100).toFixed(2) + '%',
        r.Pct_1Y,
        r.Shares,
        r.Value,
        r.Weight.toFixed(1) + '%'
    ]);

    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `hqm_portfolio_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
}
