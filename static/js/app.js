/**
 * HQM Momentum Scanner - Frontend JavaScript
 * Enhanced with watchlist, portfolio tracking, backtesting, and more.
 */

// =============================================================================
// STATE & CONFIGURATION
// =============================================================================

let scanResults = null;
let allocationChart = null;
let hqmChart = null;
let sectorChart = null;
let backtestChart = null;
let statusPollInterval = null;
let hasData = false;
let currentTheme = localStorage.getItem('theme') || 'dark';
let currentSortColumn = null;
let currentSortDirection = 'desc';

// =============================================================================
// DOM ELEMENTS
// =============================================================================

// Scanner elements
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
const addAllToWatchlistBtn = document.getElementById('addAllToWatchlistBtn');

// Refresh elements
const refreshBtn = document.getElementById('refreshBtn');
const refreshProgress = document.getElementById('refreshProgress');
const refreshProgressBar = document.getElementById('refreshProgressBar');
const refreshMessage = document.getElementById('refreshMessage');
const stockCountDisplay = document.getElementById('stockCount');
const dataAgeDisplay = document.getElementById('dataAge');
const lastRefreshDisplay = document.getElementById('lastRefresh');
const noDataAlert = document.getElementById('noDataAlert');

// Filter elements
const enableSma10Filter = document.getElementById('enableSma10Filter');
const sma10FilterControls = document.getElementById('sma10FilterControls');
const maxSma10DistanceInput = document.getElementById('maxSma10Distance');
const maxSma10Display = document.getElementById('maxSma10Display');
const enableRsiFilter = document.getElementById('enableRsiFilter');
const rsiFilterControls = document.getElementById('rsiFilterControls');
const maxRsiInput = document.getElementById('maxRsi');
const maxRsiDisplay = document.getElementById('maxRsiDisplay');
const enableVolumeFilter = document.getElementById('enableVolumeFilter');
const volumeFilterControls = document.getElementById('volumeFilterControls');
const enableDiversification = document.getElementById('enableDiversification');
const diversificationControls = document.getElementById('diversificationControls');

// Theme elements
const themeToggle = document.getElementById('themeToggle');
const themeIcon = document.getElementById('themeIcon');

// =============================================================================
// INITIALIZATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Load preferences
    loadPreferences();
    applyTheme(currentTheme);

    // Initial data fetch
    updatePositionCalculations();
    fetchDataStatus();

    // Scanner event listeners
    numPositionsInput.addEventListener('input', updatePositionCalculations);
    portfolioSizeInput.addEventListener('input', updatePositionCalculations);
    scanForm.addEventListener('submit', handleScanSubmit);
    refreshBtn.addEventListener('click', handleRefresh);
    exportBtn.addEventListener('click', exportToCSV);
    addAllToWatchlistBtn?.addEventListener('click', addAllToWatchlist);

    // Filter event listeners
    enableSma10Filter.addEventListener('change', () => toggleFilterControls('sma10'));
    maxSma10DistanceInput.addEventListener('input', updateSma10Display);
    enableRsiFilter.addEventListener('change', () => toggleFilterControls('rsi'));
    maxRsiInput.addEventListener('input', updateRsiDisplay);
    enableVolumeFilter.addEventListener('change', () => toggleFilterControls('volume'));
    enableDiversification.addEventListener('change', () => toggleFilterControls('diversification'));

    // Theme toggle
    themeToggle.addEventListener('click', toggleTheme);

    // Sortable table headers
    document.querySelectorAll('.sortable').forEach(th => {
        th.addEventListener('click', () => handleSort(th.dataset.sort));
        th.style.cursor = 'pointer';
    });

    // Tab change handlers
    document.getElementById('watchlist-tab')?.addEventListener('shown.bs.tab', loadWatchlist);
    document.getElementById('portfolio-tab')?.addEventListener('shown.bs.tab', loadPortfolio);
    document.getElementById('sectors-tab')?.addEventListener('shown.bs.tab', loadSectors);
    document.getElementById('backtest-tab')?.addEventListener('shown.bs.tab', loadBacktestHistory);

    // Watchlist form
    document.getElementById('addWatchlistForm')?.addEventListener('submit', handleAddToWatchlist);

    // Portfolio form
    document.getElementById('addPositionForm')?.addEventListener('submit', handleAddPosition);
    document.getElementById('showClosedPositions')?.addEventListener('change', loadPortfolio);
    document.getElementById('confirmClosePosition')?.addEventListener('click', handleClosePosition);

    // Backtest form
    document.getElementById('backtestForm')?.addEventListener('submit', handleBacktest);
    setDefaultBacktestDates();

    // Poll data status periodically
    setInterval(fetchDataStatus, 60000);

    // Save preferences on input change
    portfolioSizeInput.addEventListener('change', savePreferences);
    numPositionsInput.addEventListener('change', savePreferences);
});

// =============================================================================
// PREFERENCES & THEME
// =============================================================================

function loadPreferences() {
    const prefs = JSON.parse(localStorage.getItem('hqmPreferences') || '{}');
    if (prefs.portfolioSize) portfolioSizeInput.value = prefs.portfolioSize;
    if (prefs.numPositions) numPositionsInput.value = prefs.numPositions;
}

function savePreferences() {
    localStorage.setItem('hqmPreferences', JSON.stringify({
        portfolioSize: portfolioSizeInput.value,
        numPositions: numPositionsInput.value
    }));
}

function toggleTheme() {
    currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
    applyTheme(currentTheme);
    localStorage.setItem('theme', currentTheme);
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme);
    themeIcon.className = theme === 'dark' ? 'bi bi-moon-fill' : 'bi bi-sun-fill';
}

// =============================================================================
// FILTER CONTROLS
// =============================================================================

function toggleFilterControls(filter) {
    const mappings = {
        'sma10': { checkbox: enableSma10Filter, controls: sma10FilterControls },
        'rsi': { checkbox: enableRsiFilter, controls: rsiFilterControls },
        'volume': { checkbox: enableVolumeFilter, controls: volumeFilterControls },
        'diversification': { checkbox: enableDiversification, controls: diversificationControls }
    };
    const { checkbox, controls } = mappings[filter];
    controls.classList.toggle('d-none', !checkbox.checked);
}

function updateSma10Display() {
    const value = parseInt(maxSma10DistanceInput.value);
    maxSma10Display.textContent = `Max +${value}%`;
}

function updateRsiDisplay() {
    const value = parseInt(maxRsiInput.value);
    maxRsiDisplay.textContent = `RSI < ${value}`;
}

// =============================================================================
// DATA STATUS
// =============================================================================

async function fetchDataStatus() {
    try {
        const response = await fetch('/api/data-status');
        const data = await response.json();

        hasData = data.has_data;
        stockCountDisplay.textContent = data.stock_count.toLocaleString();

        if (data.data_age_hours === null || data.data_age_hours === Infinity) {
            dataAgeDisplay.textContent = 'No data';
            dataAgeDisplay.className = 'fw-bold text-warning';
        } else if (data.data_age_hours < 1) {
            dataAgeDisplay.textContent = '< 1 hour';
            dataAgeDisplay.className = 'fw-bold text-success';
        } else if (data.data_age_hours < 4) {
            dataAgeDisplay.textContent = `${data.data_age_hours.toFixed(1)} hours`;
            dataAgeDisplay.className = 'fw-bold text-success';
        } else if (data.data_age_hours < 24) {
            dataAgeDisplay.textContent = `${Math.round(data.data_age_hours)} hours`;
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

// =============================================================================
// REFRESH HANDLING
// =============================================================================

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

        startStatusPolling('refresh');
    } catch (error) {
        console.error('Refresh error:', error);
        alert('Failed to start refresh. Please try again.');
        resetRefreshButton();
    }
}

function resetRefreshButton() {
    refreshBtn.disabled = false;
    refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i>Refresh';
    refreshProgress.classList.add('d-none');
}

// =============================================================================
// SCAN HANDLING
// =============================================================================

function updatePositionCalculations() {
    const portfolioSize = parseFloat(portfolioSizeInput.value) || 10000;
    const numPositions = parseInt(numPositionsInput.value) || 8;

    const positionSize = portfolioSize / numPositions;
    const positionWeight = 100 / numPositions;

    numPositionsDisplay.textContent = `${numPositions} stocks`;
    positionSizeDisplay.textContent = `$${positionSize.toLocaleString('en-US', {maximumFractionDigits: 0})}`;
    positionWeightDisplay.textContent = `${positionWeight.toFixed(1)}%`;
}

async function handleScanSubmit(e) {
    e.preventDefault();

    if (!hasData) {
        alert('Please refresh data first.');
        return;
    }

    const portfolioSize = parseFloat(portfolioSizeInput.value);
    const numPositions = parseInt(numPositionsInput.value);

    if (portfolioSize < 1000) {
        alert('Portfolio size must be at least $1,000');
        return;
    }

    // Build request body with filters
    const body = {
        portfolio_size: portfolioSize,
        num_positions: numPositions,
        max_sma10_distance: enableSma10Filter.checked ? parseInt(maxSma10DistanceInput.value) : null,
        rsi_enabled: enableRsiFilter.checked,
        rsi_min: 0,
        rsi_max: enableRsiFilter.checked ? parseInt(maxRsiInput.value) : 100,
        volume_enabled: enableVolumeFilter.checked,
        min_volume: enableVolumeFilter.checked ? parseInt(document.getElementById('minVolume').value) : null,
        diversification_enabled: enableDiversification.checked,
        max_per_sector: enableDiversification.checked ? parseInt(document.getElementById('maxPerSector').value) : null
    };

    try {
        const response = await fetch('/api/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        const data = await response.json();

        if (!data.success) {
            alert(data.error || 'Failed to start scan');
            return;
        }

        showProgress();
        startStatusPolling('scan');
    } catch (error) {
        console.error('Scan error:', error);
        alert('Failed to start scan. Please try again.');
    }
}

function showProgress() {
    scanBtn.classList.add('scanning');
    scanBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Scanning...';
    scanBtn.disabled = true;
    progressSection.classList.remove('d-none');
    progressBar.style.width = '0%';
}

function hideProgress() {
    scanBtn.classList.remove('scanning');
    scanBtn.innerHTML = '<i class="bi bi-search me-2"></i>Run Scan';
    scanBtn.disabled = false;
    progressSection.classList.add('d-none');
}

// =============================================================================
// STATUS POLLING
// =============================================================================

function startStatusPolling(type) {
    if (statusPollInterval) {
        clearInterval(statusPollInterval);
    }

    statusPollInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();

            if (type === 'refresh') {
                refreshProgressBar.style.width = `${data.progress}%`;
                refreshMessage.textContent = data.message;

                if (data.status === 'completed' || data.status === 'idle') {
                    clearInterval(statusPollInterval);
                    resetRefreshButton();
                    fetchDataStatus();
                } else if (data.status === 'error') {
                    clearInterval(statusPollInterval);
                    resetRefreshButton();
                    alert('Refresh failed: ' + data.message);
                }
            } else if (type === 'scan') {
                progressBar.style.width = `${data.progress}%`;
                progressMessage.textContent = data.message;

                if (data.status === 'completed') {
                    clearInterval(statusPollInterval);
                    hideProgress();
                    fetchResults();
                } else if (data.status === 'error') {
                    clearInterval(statusPollInterval);
                    hideProgress();
                    alert('Scan failed: ' + data.message);
                }
            } else if (type === 'backtest') {
                document.getElementById('backtestProgressBar').style.width = `${data.progress}%`;
                document.getElementById('backtestMessage').textContent = data.message;

                if (data.status === 'completed') {
                    clearInterval(statusPollInterval);
                    document.getElementById('backtestProgress').classList.add('d-none');
                    document.getElementById('backtestBtn').disabled = false;
                    fetchBacktestResults();
                } else if (data.status === 'error') {
                    clearInterval(statusPollInterval);
                    document.getElementById('backtestProgress').classList.add('d-none');
                    document.getElementById('backtestBtn').disabled = false;
                    alert('Backtest failed: ' + data.message);
                }
            }
        } catch (error) {
            console.error('Status poll error:', error);
        }
    }, 300);
}

// =============================================================================
// RESULTS DISPLAY
// =============================================================================

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

function displayResults(results, summary) {
    emptyState.classList.add('d-none');
    resultsTable.classList.remove('d-none');
    summaryCard.classList.remove('d-none');
    chartsRow.classList.remove('d-none');
    legendCard.classList.remove('d-none');
    exportBtn.classList.remove('d-none');
    addAllToWatchlistBtn?.classList.remove('d-none');

    // Update summary
    document.getElementById('summaryScanned').textContent = summary.total_scanned.toLocaleString();
    document.getElementById('summaryFiltered').textContent = summary.after_quality_filter.toLocaleString();
    document.getElementById('summaryInvested').textContent = `$${summary.total_invested.toLocaleString()}`;
    document.getElementById('summaryCash').textContent = `$${summary.cash_remaining.toLocaleString()}`;

    // Update risk metrics if available
    if (summary.risk_metrics) {
        const rm = summary.risk_metrics;
        document.getElementById('sharpeRatio').textContent = rm.sharpe_ratio?.toFixed(2) || '-';
        document.getElementById('portfolioBeta').textContent = rm.portfolio_beta?.toFixed(2) || '-';
        document.getElementById('maxDrawdown').textContent = rm.max_drawdown ? `${rm.max_drawdown.toFixed(1)}%` : '-';
        document.getElementById('var95').textContent = rm.var_95 ? `$${rm.var_95.toLocaleString()}` : '-';
    }

    // Build table
    resultsBody.innerHTML = results.map((stock, index) => `
        <tr data-ticker="${stock.Ticker}">
            <td class="text-muted">${index + 1}</td>
            <td class="ticker-cell">
                <a href="https://www.tradingview.com/chart/?symbol=${stock.Exchange}%3A${stock.Ticker}"
                   target="_blank" class="ticker-link" title="View on TradingView">
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
                    ${stock.HQM_Score.toFixed(1)}
                </span>
            </td>
            <td>${formatSma10Distance(stock.SMA10_Distance)}</td>
            <td>${formatRsi(stock.RSI)}</td>
            <td><span class="badge bg-secondary">${stock.Sector || '-'}</span></td>
            <td>${formatReturn(stock.Return_1M, stock.Pct_1M)}</td>
            <td>${formatReturn(stock.Return_3M, stock.Pct_3M)}</td>
            <td>${formatReturn(stock.Return_6M, stock.Pct_6M)}</td>
            <td>${formatReturn(stock.Return_1Y, stock.Pct_1Y)}</td>
            <td class="fw-bold">${stock.Shares}</td>
            <td class="text-success">$${stock.Value.toLocaleString()}</td>
            <td>
                <button class="btn btn-outline-info btn-sm" onclick="addSingleToWatchlist('${stock.Ticker}')" title="Add to watchlist">
                    <i class="bi bi-eye"></i>
                </button>
            </td>
        </tr>
    `).join('');

    updateCharts(results);
}

// =============================================================================
// FORMATTING HELPERS
// =============================================================================

function formatReturn(returnVal, percentile) {
    if (returnVal === null || returnVal === undefined) return '-';
    const pctClass = getPctClass(percentile);
    const returnClass = returnVal >= 0 ? 'return-positive' : 'return-negative';
    const sign = returnVal >= 0 ? '+' : '';
    return `
        <span class="pct-indicator ${pctClass}"></span>
        <span class="${returnClass}">${sign}${(returnVal * 100).toFixed(1)}%</span>
    `;
}

function getPctClass(percentile) {
    if (percentile >= 75) return 'pct-high';
    if (percentile >= 50) return 'pct-medium';
    if (percentile >= 25) return 'pct-low';
    return 'pct-very-low';
}

function formatSma10Distance(distance) {
    if (distance === null || distance === undefined) return '<span class="text-muted">-</span>';
    const sign = distance >= 0 ? '+' : '';
    let colorClass = 'sma10-good';
    let icon = 'bi-check-circle-fill';

    if (distance > 15) {
        colorClass = 'sma10-extended';
        icon = 'bi-exclamation-triangle-fill';
    } else if (distance > 8) {
        colorClass = 'sma10-moderate';
        icon = 'bi-dash-circle-fill';
    }

    return `<span class="${colorClass}" title="Distance from SMA10">
        <i class="bi ${icon} me-1 small"></i>${sign}${distance.toFixed(1)}%
    </span>`;
}

function formatRsi(rsi) {
    if (rsi === null || rsi === undefined) return '<span class="text-muted">-</span>';
    let colorClass = '';
    if (rsi >= 70) colorClass = 'text-danger';
    else if (rsi <= 30) colorClass = 'text-success';
    return `<span class="${colorClass}">${rsi.toFixed(0)}</span>`;
}

// =============================================================================
// SORTING
// =============================================================================

function handleSort(column) {
    if (currentSortColumn === column) {
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortColumn = column;
        currentSortDirection = 'desc';
    }

    if (!scanResults?.results) return;

    const sortedResults = [...scanResults.results].sort((a, b) => {
        let aVal, bVal;
        switch (column) {
            case 'ticker': aVal = a.Ticker; bVal = b.Ticker; break;
            case 'price': aVal = a.Price; bVal = b.Price; break;
            case 'hqm': aVal = a.HQM_Score; bVal = b.HQM_Score; break;
            case 'sma10': aVal = a.SMA10_Distance || 0; bVal = b.SMA10_Distance || 0; break;
            case 'rsi': aVal = a.RSI || 0; bVal = b.RSI || 0; break;
            case 'sector': aVal = a.Sector || ''; bVal = b.Sector || ''; break;
            case 'return1m': aVal = a.Return_1M; bVal = b.Return_1M; break;
            case 'return3m': aVal = a.Return_3M; bVal = b.Return_3M; break;
            case 'return6m': aVal = a.Return_6M; bVal = b.Return_6M; break;
            case 'return1y': aVal = a.Return_1Y; bVal = b.Return_1Y; break;
            default: return 0;
        }

        if (typeof aVal === 'string') {
            return currentSortDirection === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
        }
        return currentSortDirection === 'asc' ? aVal - bVal : bVal - aVal;
    });

    displayResults(sortedResults, scanResults.summary);

    // Update sort indicators
    document.querySelectorAll('.sortable').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
        if (th.dataset.sort === column) {
            th.classList.add(currentSortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    });
}

// =============================================================================
// CHARTS
// =============================================================================

function updateCharts(results) {
    const tickers = results.map(r => r.Ticker);
    const values = results.map(r => r.Value);
    const hqmScores = results.map(r => r.HQM_Score);

    const colors = [
        '#198754', '#20c997', '#0dcaf0', '#0d6efd',
        '#6610f2', '#6f42c1', '#d63384', '#dc3545',
        '#fd7e14', '#ffc107', '#28a745', '#17a2b8'
    ];

    if (allocationChart) allocationChart.destroy();
    if (hqmChart) hqmChart.destroy();

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
                    labels: { color: '#adb5bd', padding: 10, font: { size: 11 } }
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

    const hqmCtx = document.getElementById('hqmChart').getContext('2d');
    hqmChart = new Chart(hqmCtx, {
        type: 'bar',
        data: {
            labels: tickers,
            datasets: [{
                label: 'HQM Score',
                data: hqmScores,
                backgroundColor: hqmScores.map(score =>
                    score >= 95 ? '#198754' : score >= 90 ? '#20c997' : score >= 85 ? '#0dcaf0' : '#0d6efd'
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
                x: { min: 80, max: 100, grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#adb5bd' } },
                y: { grid: { display: false }, ticks: { color: '#adb5bd', font: { weight: 'bold' } } }
            },
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: (context) => `HQM Score: ${context.raw.toFixed(1)}` } }
            }
        }
    });
}

// =============================================================================
// EXPORT
// =============================================================================

function exportToCSV() {
    if (!scanResults?.results) {
        alert('No results to export');
        return;
    }

    const headers = [
        'Ticker', 'Price', 'Market Cap', 'Exchange', 'Sector',
        'SMA10 Distance', 'RSI', 'HQM Score',
        '1M Return', '1M Pct', '3M Return', '3M Pct',
        '6M Return', '6M Pct', '1Y Return', '1Y Pct',
        'Shares', 'Value', 'Weight'
    ];

    const rows = scanResults.results.map(r => [
        r.Ticker, r.Price, r.Market_Cap_Display, r.Exchange, r.Sector || '',
        r.SMA10_Distance !== null ? r.SMA10_Distance.toFixed(1) + '%' : '-',
        r.RSI !== null ? r.RSI.toFixed(0) : '-',
        r.HQM_Score.toFixed(1),
        (r.Return_1M * 100).toFixed(2) + '%', r.Pct_1M.toFixed(1),
        (r.Return_3M * 100).toFixed(2) + '%', r.Pct_3M.toFixed(1),
        (r.Return_6M * 100).toFixed(2) + '%', r.Pct_6M.toFixed(1),
        (r.Return_1Y * 100).toFixed(2) + '%', r.Pct_1Y.toFixed(1),
        r.Shares, r.Value.toFixed(2), r.Weight.toFixed(1) + '%'
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

// =============================================================================
// WATCHLIST
// =============================================================================

async function loadWatchlist() {
    try {
        const response = await fetch('/api/watchlist');
        const data = await response.json();

        const tbody = document.getElementById('watchlistBody');
        if (!data.success || !data.watchlist.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">No items in watchlist</td></tr>';
            return;
        }

        tbody.innerHTML = data.watchlist.map(item => `
            <tr>
                <td class="fw-bold">${item.ticker}</td>
                <td>${item.price ? '$' + item.price.toFixed(2) : '-'}</td>
                <td>${item.target_entry_price ? '$' + item.target_entry_price.toFixed(2) : '-'}</td>
                <td class="${(item.return_1m || 0) >= 0 ? 'text-success' : 'text-danger'}">
                    ${item.return_1m ? (item.return_1m * 100).toFixed(1) + '%' : '-'}
                </td>
                <td>${item.sector || '-'}</td>
                <td class="small">${new Date(item.added_date).toLocaleDateString()}</td>
                <td class="small">${item.notes || '-'}</td>
                <td>
                    <button class="btn btn-outline-danger btn-sm" onclick="removeFromWatchlist('${item.ticker}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Failed to load watchlist:', error);
    }
}

async function handleAddToWatchlist(e) {
    e.preventDefault();
    const ticker = document.getElementById('watchlistTicker').value.trim().toUpperCase();
    const targetPrice = document.getElementById('watchlistTargetPrice').value;
    const notes = document.getElementById('watchlistNotes').value;

    if (!ticker) return;

    try {
        const response = await fetch('/api/watchlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker, target_price: targetPrice || null, notes: notes || null })
        });
        const data = await response.json();

        if (data.success) {
            document.getElementById('addWatchlistForm').reset();
            loadWatchlist();
        } else {
            alert(data.error);
        }
    } catch (error) {
        console.error('Failed to add to watchlist:', error);
    }
}

async function removeFromWatchlist(ticker) {
    if (!confirm(`Remove ${ticker} from watchlist?`)) return;

    try {
        const response = await fetch(`/api/watchlist/${ticker}`, { method: 'DELETE' });
        const data = await response.json();

        if (data.success) {
            loadWatchlist();
        } else {
            alert(data.error);
        }
    } catch (error) {
        console.error('Failed to remove from watchlist:', error);
    }
}

async function addSingleToWatchlist(ticker) {
    try {
        const response = await fetch('/api/watchlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker })
        });
        const data = await response.json();
        alert(data.success ? `${ticker} added to watchlist` : data.error);
    } catch (error) {
        console.error('Failed to add to watchlist:', error);
    }
}

async function addAllToWatchlist() {
    if (!scanResults?.results) return;
    for (const stock of scanResults.results) {
        await addSingleToWatchlist(stock.Ticker);
    }
    alert('All stocks added to watchlist');
}

// =============================================================================
// PORTFOLIO TRACKING
// =============================================================================

async function loadPortfolio() {
    const includeClosed = document.getElementById('showClosedPositions')?.checked || false;

    try {
        const response = await fetch(`/api/portfolio?include_closed=${includeClosed}`);
        const data = await response.json();

        if (data.success) {
            const { positions, summary } = data;

            document.getElementById('portfolioValue').textContent = `$${summary.total_value.toLocaleString()}`;
            document.getElementById('portfolioPnl').textContent = `$${summary.total_pnl.toLocaleString()}`;
            document.getElementById('portfolioPnl').className = `fs-4 fw-bold ${summary.total_pnl >= 0 ? 'text-success' : 'text-danger'}`;
            document.getElementById('portfolioCount').textContent = summary.position_count;
            const winRate = summary.position_count > 0 ? (summary.winning_positions / summary.position_count * 100).toFixed(0) : 0;
            document.getElementById('portfolioWinRate').textContent = `${winRate}%`;

            const tbody = document.getElementById('portfolioBody');
            if (!positions.length) {
                tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">No positions</td></tr>';
                return;
            }

            tbody.innerHTML = positions.map(pos => `
                <tr class="${pos.status === 'closed' ? 'text-muted' : ''}">
                    <td class="fw-bold">${pos.ticker}</td>
                    <td>${pos.shares}</td>
                    <td>$${pos.entry_price.toFixed(2)}</td>
                    <td>${pos.current_price ? '$' + pos.current_price.toFixed(2) : '-'}</td>
                    <td class="${(pos.unrealized_pnl || 0) >= 0 ? 'text-success' : 'text-danger'}">
                        ${pos.unrealized_pnl ? '$' + pos.unrealized_pnl.toFixed(2) : '-'}
                    </td>
                    <td class="${(pos.unrealized_pnl_pct || 0) >= 0 ? 'text-success' : 'text-danger'}">
                        ${pos.unrealized_pnl_pct ? pos.unrealized_pnl_pct.toFixed(1) + '%' : '-'}
                    </td>
                    <td>$${pos.current_price ? (pos.shares * pos.current_price).toFixed(2) : '-'}</td>
                    <td>
                        ${pos.status === 'open' ? `
                            <button class="btn btn-outline-warning btn-sm" onclick="openClosePositionModal(${pos.id}, '${pos.ticker}', ${pos.current_price || pos.entry_price})">
                                <i class="bi bi-x-circle"></i>
                            </button>
                        ` : '<span class="badge bg-secondary">Closed</span>'}
                    </td>
                </tr>
            `).join('');
        }
    } catch (error) {
        console.error('Failed to load portfolio:', error);
    }
}

async function handleAddPosition(e) {
    e.preventDefault();
    const ticker = document.getElementById('positionTicker').value.trim().toUpperCase();
    const shares = parseInt(document.getElementById('positionShares').value);
    const entryPrice = parseFloat(document.getElementById('positionPrice').value);
    const entryDate = document.getElementById('positionDate').value || null;

    try {
        const response = await fetch('/api/portfolio', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker, shares, entry_price: entryPrice, entry_date: entryDate })
        });
        const data = await response.json();

        if (data.success) {
            document.getElementById('addPositionForm').reset();
            loadPortfolio();
        } else {
            alert(data.error);
        }
    } catch (error) {
        console.error('Failed to add position:', error);
    }
}

function openClosePositionModal(positionId, ticker, currentPrice) {
    document.getElementById('closePositionId').value = positionId;
    document.getElementById('closePositionTicker').textContent = ticker;
    document.getElementById('exitPrice').value = currentPrice.toFixed(2);
    new bootstrap.Modal(document.getElementById('closePositionModal')).show();
}

async function handleClosePosition() {
    const positionId = document.getElementById('closePositionId').value;
    const exitPrice = parseFloat(document.getElementById('exitPrice').value);

    try {
        const response = await fetch(`/api/portfolio/${positionId}/close`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ exit_price: exitPrice })
        });
        const data = await response.json();

        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('closePositionModal')).hide();
            loadPortfolio();
        } else {
            alert(data.error);
        }
    } catch (error) {
        console.error('Failed to close position:', error);
    }
}

// =============================================================================
// SECTORS
// =============================================================================

async function loadSectors() {
    try {
        const response = await fetch('/api/sectors');
        const data = await response.json();

        if (!data.success) return;

        const { breakdown } = data;

        // Update table
        const tbody = document.getElementById('sectorTableBody');
        tbody.innerHTML = breakdown.map(s => `
            <tr>
                <td class="fw-bold">${s.Sector}</td>
                <td>${s.Count}</td>
                <td class="${(s.Avg_Return_1M || 0) >= 0 ? 'text-success' : 'text-danger'}">
                    ${s.Avg_Return_1M ? (s.Avg_Return_1M * 100).toFixed(1) + '%' : '-'}
                </td>
                <td class="${(s.Avg_Return_3M || 0) >= 0 ? 'text-success' : 'text-danger'}">
                    ${s.Avg_Return_3M ? (s.Avg_Return_3M * 100).toFixed(1) + '%' : '-'}
                </td>
                <td class="${(s.Avg_Return_6M || 0) >= 0 ? 'text-success' : 'text-danger'}">
                    ${s.Avg_Return_6M ? (s.Avg_Return_6M * 100).toFixed(1) + '%' : '-'}
                </td>
            </tr>
        `).join('');

        // Update chart
        if (sectorChart) sectorChart.destroy();
        const ctx = document.getElementById('sectorChart').getContext('2d');
        sectorChart = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: breakdown.map(s => s.Sector),
                datasets: [{
                    data: breakdown.map(s => s.Count),
                    backgroundColor: [
                        '#198754', '#20c997', '#0dcaf0', '#0d6efd', '#6610f2',
                        '#6f42c1', '#d63384', '#dc3545', '#fd7e14', '#ffc107', '#6c757d'
                    ]
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'right', labels: { color: '#adb5bd', font: { size: 10 } } }
                }
            }
        });
    } catch (error) {
        console.error('Failed to load sectors:', error);
    }
}

// =============================================================================
// BACKTESTING
// =============================================================================

function setDefaultBacktestDates() {
    const today = new Date();
    const oneYearAgo = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate());

    document.getElementById('backtestEnd').value = today.toISOString().split('T')[0];
    document.getElementById('backtestStart').value = oneYearAgo.toISOString().split('T')[0];
}

async function handleBacktest(e) {
    e.preventDefault();

    const startDate = document.getElementById('backtestStart').value;
    const endDate = document.getElementById('backtestEnd').value;
    const initialCapital = parseFloat(document.getElementById('backtestCapital').value);
    const numPositions = parseInt(document.getElementById('backtestPositions').value);
    const frequency = document.getElementById('backtestFrequency').value;

    document.getElementById('backtestBtn').disabled = true;
    document.getElementById('backtestProgress').classList.remove('d-none');

    try {
        const response = await fetch('/api/backtest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start_date: startDate,
                end_date: endDate,
                initial_capital: initialCapital,
                num_positions: numPositions,
                rebalance_frequency: frequency
            })
        });
        const data = await response.json();

        if (data.success) {
            startStatusPolling('backtest');
        } else {
            alert(data.error);
            document.getElementById('backtestBtn').disabled = false;
            document.getElementById('backtestProgress').classList.add('d-none');
        }
    } catch (error) {
        console.error('Failed to start backtest:', error);
        document.getElementById('backtestBtn').disabled = false;
        document.getElementById('backtestProgress').classList.add('d-none');
    }
}

async function fetchBacktestResults() {
    try {
        const response = await fetch('/api/backtest/results');
        const data = await response.json();

        if (data.success && data.results) {
            displayBacktestResults(data.results);
        }

        loadBacktestHistory();
    } catch (error) {
        console.error('Failed to fetch backtest results:', error);
    }
}

function displayBacktestResults(results) {
    document.getElementById('backtestResultsCard').style.display = 'block';

    const returnClass = results.total_return >= 0 ? 'text-success' : 'text-danger';
    document.getElementById('btTotalReturn').className = `fs-4 fw-bold ${returnClass}`;
    document.getElementById('btTotalReturn').textContent = `${results.total_return >= 0 ? '+' : ''}${results.total_return.toFixed(1)}%`;
    document.getElementById('btSharpe').textContent = results.sharpe_ratio.toFixed(2);
    document.getElementById('btDrawdown').textContent = `${results.max_drawdown.toFixed(1)}%`;
    document.getElementById('btWinRate').textContent = `${results.win_rate.toFixed(0)}%`;

    // Draw equity curve
    if (backtestChart) backtestChart.destroy();
    const ctx = document.getElementById('backtestChart').getContext('2d');

    const history = results.portfolio_history || [];
    backtestChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: history.map(h => new Date(h.date).toLocaleDateString()),
            datasets: [{
                label: 'Portfolio Value',
                data: history.map(h => h.total_value),
                borderColor: '#20c997',
                backgroundColor: 'rgba(32, 201, 151, 0.1)',
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#adb5bd', maxTicksLimit: 10 } },
                y: {
                    grid: { color: 'rgba(255,255,255,0.1)' },
                    ticks: {
                        color: '#adb5bd',
                        callback: value => '$' + value.toLocaleString()
                    }
                }
            }
        }
    });
}

async function loadBacktestHistory() {
    try {
        const response = await fetch('/api/backtest/history');
        const data = await response.json();

        const tbody = document.getElementById('backtestHistoryBody');
        if (!data.success || !data.history.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">No backtest history</td></tr>';
            return;
        }

        tbody.innerHTML = data.history.map(bt => `
            <tr>
                <td>${new Date(bt.run_date).toLocaleDateString()}</td>
                <td>${bt.start_date} - ${bt.end_date}</td>
                <td class="${bt.total_return >= 0 ? 'text-success' : 'text-danger'}">
                    ${bt.total_return >= 0 ? '+' : ''}${bt.total_return.toFixed(1)}%
                </td>
                <td>${bt.sharpe_ratio.toFixed(2)}</td>
                <td class="text-danger">${bt.max_drawdown.toFixed(1)}%</td>
                <td>${bt.num_trades}</td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Failed to load backtest history:', error);
    }
}
