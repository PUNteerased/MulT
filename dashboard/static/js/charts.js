/**
 * Deep-Sniper AI Chart.js Visualizations.
 * 1. Real-time RTX 4050 VRAM usage history (monitoring dynamic lifecycle).
 * 2. Cumulative Equity & PnL curve.
 */

let vramChart = null;
let equityChart = null;

const VRAM_MAX_POINTS = 30;
const vramHistory = {
  labels: [],
  data: [],
  threshold: []
};

function initVramChart() {
  const ctx = document.getElementById('vramHistoryChart');
  if (!ctx) return;

  vramChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: vramHistory.labels,
      datasets: [
        {
          label: 'VRAM Used (MB)',
          data: vramHistory.data,
          borderColor: '#06b6d4',
          backgroundColor: 'rgba(6, 182, 212, 0.1)',
          borderWidth: 2,
          fill: true,
          tension: 0.3,
          pointRadius: 1,
        },
        {
          label: 'Safe Ceiling (2500 MB)',
          data: vramHistory.threshold,
          borderColor: 'rgba(244, 63, 94, 0.7)',
          borderWidth: 1.5,
          borderDash: [5, 5],
          fill: false,
          pointRadius: 0,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          labels: { color: '#94a3b8', font: { size: 10 } }
        },
        tooltip: {
          mode: 'index',
          intersect: false
        }
      },
      scales: {
        x: {
          display: false,
          grid: { display: false }
        },
        y: {
          min: 0,
          max: 4000,
          grid: { color: 'rgba(51, 65, 85, 0.3)' },
          ticks: {
            color: '#64748b',
            font: { size: 10 },
            callback: (v) => v + ' MB'
          }
        }
      }
    }
  });
}

function updateVramChart(usedMb) {
  if (!vramChart) return;

  const now = new Date().toLocaleTimeString();
  vramHistory.labels.push(now);
  vramHistory.data.push(usedMb);
  vramHistory.threshold.push(2500);

  if (vramHistory.labels.length > VRAM_MAX_POINTS) {
    vramHistory.labels.shift();
    vramHistory.data.shift();
    vramHistory.threshold.shift();
  }

  vramChart.update('none');
}

function initEquityChart(trades = []) {
  const ctx = document.getElementById('equityCurveChart');
  if (!ctx) return;

  const labels = ['Start'];
  const data = [50.0]; // Initial $50 account balance
  let runningBalance = 50.0;

  // Trades sorted chronologically
  const sorted = [...trades].sort((a, b) => (a.entry_timestamp || 0) - (b.entry_timestamp || 0));

  sorted.forEach((t, i) => {
    runningBalance += (t.pnl || 0);
    labels.push(`T#${i + 1}`);
    data.push(parseFloat(runningBalance.toFixed(2)));
  });

  if (equityChart) {
    equityChart.data.labels = labels;
    equityChart.data.datasets[0].data = data;
    equityChart.update();
    return;
  }

  equityChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Account Equity ($)',
          data: data,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.12)',
          borderWidth: 2.5,
          fill: true,
          tension: 0.2,
          pointRadius: 3,
          pointHoverRadius: 5
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          callbacks: {
            label: (ctx) => `Equity: $${ctx.parsed.y.toFixed(2)}`
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(51, 65, 85, 0.2)' },
          ticks: { color: '#64748b', font: { size: 10 } }
        },
        y: {
          grid: { color: 'rgba(51, 65, 85, 0.3)' },
          ticks: {
            color: '#64748b',
            font: { size: 10 },
            callback: (v) => '$' + v
          }
        }
      }
    }
  });
}
