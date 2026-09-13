/**
 * Deep-Sniper AI Master Dashboard Controller.
 * Handles WebSocket communication, UI state, active position progress,
 * and API synchronization across devices.
 */

class DashboardApp {
  constructor() {
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 10000;
    this.activePosition = null;
    this.activeKillZones = {};
    this.latestPrices = {};
    this.backendUrl = localStorage.getItem('mulT_backend_url') || window.location.origin;

    this.initElements();
    this.bindEvents();
    this.loadInitialData();
    this.connectWebSocket();

    // Heartbeat ping every 15s
    setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ action: 'ping' }));
      }
    }, 15000);
  }

  getWsUrl() {
    let base = this.backendUrl;
    if (!base.startsWith('http')) {
      base = window.location.origin;
    }
    const wsProto = base.startsWith('https') ? 'wss:' : 'ws:';
    const host = base.replace(/^https?:\/\//, '').replace(/\/$/, '');
    return `${wsProto}//${host}/ws`;
  }

  getApiUrl(endpoint) {
    const base = this.backendUrl.replace(/\/$/, '');
    return `${base}${endpoint}`;
  }

  initElements() {
    this.el = {
      connectionStatus: document.getElementById('connectionStatus'),
      connectionDot: document.getElementById('connectionDot'),
      redFolderBanner: document.getElementById('redFolderBanner'),
      redFolderText: document.getElementById('redFolderText'),

      // Hardware
      vramProgress: document.getElementById('vramProgress'),
      vramUsedText: document.getElementById('vramUsedText'),
      vramPercentText: document.getElementById('vramPercentText'),
      vramBadge: document.getElementById('vramBadge'),
      cpuPercentText: document.getElementById('cpuPercentText'),
      cpuProgress: document.getElementById('cpuProgress'),
      ramUsedText: document.getElementById('ramUsedText'),
      ramProgress: document.getElementById('ramProgress'),

      // Account
      accountBalance: document.getElementById('accountBalance'),
      accountEquity: document.getElementById('accountEquity'),
      accountFloatingPnl: document.getElementById('accountFloatingPnl'),
      mt5Ping: document.getElementById('mt5Ping'),
      mt5LoginServer: document.getElementById('mt5LoginServer'),

      // Analytics
      winRateText: document.getElementById('winRateText'),
      profitFactorText: document.getElementById('profitFactorText'),
      totalTradesText: document.getElementById('totalTradesText'),
      netPnlText: document.getElementById('netPnlText'),

      // Active Position
      activePositionContainer: document.getElementById('activePositionContainer'),
      noActivePositionState: document.getElementById('noActivePositionState'),
      activePosContent: document.getElementById('activePosContent'),
      activePosSymbol: document.getElementById('activePosSymbol'),
      activePosDirection: document.getElementById('activePosDirection'),
      activePosEntry: document.getElementById('activePosEntry'),
      activePosCurrent: document.getElementById('activePosCurrent'),
      activePosSl: document.getElementById('activePosSl'),
      activePosBeBadge: document.getElementById('activePosBeBadge'),
      activePosProgressBar: document.getElementById('activePosProgressBar'),

      // Radar Cards Container
      radarCardsGrid: document.getElementById('radarCardsGrid'),

      // Trades Table
      tradesTableBody: document.getElementById('tradesTableBody'),

      // Config Modal
      configModal: document.getElementById('configModal'),
      backendUrlInput: document.getElementById('backendUrlInput'),
      btnSaveConfig: document.getElementById('btnSaveConfig'),
      btnOpenConfig: document.getElementById('btnOpenConfig'),
      btnCloseConfig: document.getElementById('btnCloseConfig'),
      btnToggleSound: document.getElementById('btnToggleSound'),
    };
  }

  bindEvents() {
    if (this.el.btnToggleSound) {
      this.el.btnToggleSound.addEventListener('click', () => {
        const enabled = window.notifyManager.toggleSound();
        this.el.btnToggleSound.innerHTML = enabled
          ? '<span class="text-emerald-400">🔊 Sound On</span>'
          : '<span class="text-slate-400">🔇 Muted</span>';
      });
    }

    if (this.el.btnOpenConfig) {
      this.el.btnOpenConfig.addEventListener('click', () => {
        this.el.backendUrlInput.value = this.backendUrl;
        this.el.configModal.classList.remove('hidden');
      });
    }

    if (this.el.btnCloseConfig) {
      this.el.btnCloseConfig.addEventListener('click', () => {
        this.el.configModal.classList.add('hidden');
      });
    }

    if (this.el.btnSaveConfig) {
      this.el.btnSaveConfig.addEventListener('click', () => {
        let val = this.el.backendUrlInput.value.trim();
        if (val) {
          if (!val.startsWith('http://') && !val.startsWith('https://')) {
            val = 'https://' + val;
          }
          this.backendUrl = val;
          localStorage.setItem('mulT_backend_url', val);
          this.el.configModal.classList.add('hidden');
          window.notifyManager.showToast('Backend Updated', `Reconnecting to ${val}...`, 'info');
          if (this.ws) {
            this.ws.close();
          }
          this.connectWebSocket();
          this.loadInitialData();
        }
      });
    }
  }

  async loadInitialData() {
    try {
      const [statusRes, zonesRes, tradesRes, analyticsRes] = await Promise.all([
        fetch(this.getApiUrl('/api/status')).catch(() => null),
        fetch(this.getApiUrl('/api/kill-zones')).catch(() => null),
        fetch(this.getApiUrl('/api/trades?limit=25')).catch(() => null),
        fetch(this.getApiUrl('/api/analytics')).catch(() => null),
      ]);

      if (statusRes && statusRes.ok) {
        const statusData = await statusRes.json();
        this.updateSystemStatus(statusData);
      }

      if (zonesRes && zonesRes.ok) {
        const zonesData = await zonesRes.json();
        this.renderRadarCards(zonesData);
      }

      if (tradesRes && tradesRes.ok) {
        const tradesData = await tradesRes.json();
        this.renderTradesTable(tradesData.trades || []);
        if (typeof initEquityChart === 'function') {
          initEquityChart(tradesData.trades || []);
        }
      }

      if (analyticsRes && analyticsRes.ok) {
        const analyticsData = await analyticsRes.json();
        this.updateAnalytics(analyticsData);
      }
    } catch (e) {
      console.warn('Initial data load error:', e);
    }
  }

  connectWebSocket() {
    const wsUrl = this.getWsUrl();
    console.log('[WebSocket] Connecting to:', wsUrl);

    try {
      this.ws = new WebSocket(wsUrl);
    } catch (e) {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      console.log('[WebSocket] Connected successfully.');
      this.reconnectAttempts = 0;
      this.updateConnectionBadge(true);
      window.notifyManager.showToast('System Live', 'Connected to MulT Real-Time Bus', 'success', 3000);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this.handleWsMessage(msg);
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    };

    this.ws.onclose = () => {
      console.warn('[WebSocket] Closed. Scheduling reconnect...');
      this.updateConnectionBadge(false);
      this.scheduleReconnect();
    };

    this.ws.onerror = (err) => {
      console.error('[WebSocket] Error:', err);
      this.updateConnectionBadge(false);
    };
  }

  scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    setTimeout(() => this.connectWebSocket(), delay);
  }

  updateConnectionBadge(isOnline) {
    if (this.el.connectionDot) {
      if (isOnline) {
        this.el.connectionDot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400 pulse-emerald';
        this.el.connectionStatus.innerText = 'ONLINE';
        this.el.connectionStatus.className = 'text-emerald-400 font-semibold text-xs';
      } else {
        this.el.connectionDot.className = 'w-2.5 h-2.5 rounded-full bg-rose-500 pulse-rose';
        this.el.connectionStatus.innerText = 'RECONNECTING';
        this.el.connectionStatus.className = 'text-rose-400 font-semibold text-xs';
      }
    }
  }

  handleWsMessage(msg) {
    const type = msg.type;

    switch (type) {
      case 'telemetry':
        this.handleTelemetry(msg);
        break;

      case 'tick':
        this.handleTick(msg.data);
        break;

      case 'kill_zone':
        this.handleKillZoneUpdate(msg.data);
        break;

      case 'trigger_alert':
        this.handleTriggerAlert(msg.data);
        break;

      case 'trade_ticket':
        this.handleTradeTicket(msg.data);
        break;

      case 'execution':
        this.handleExecution(msg.data);
        break;

      case 'system_state':
        this.handleSystemState(msg.data);
        break;

      case 'event_backlog':
        if (msg.events) {
          msg.events.forEach(e => {
            if (e.type === 'execution') this.handleExecution(e.data, true);
            else if (e.type === 'trigger_alert') this.handleTriggerAlert(e.data, true);
          });
        }
        break;

      default:
        break;
    }
  }

  handleTelemetry(msg) {
    const hw = msg.hardware;
    const mt5 = msg.mt5;

    // GPU VRAM
    if (hw && hw.gpu) {
      const gpu = hw.gpu;
      const pct = gpu.vram_percent || 0;
      this.el.vramProgress.style.width = `${Math.min(pct, 100)}%`;
      this.el.vramUsedText.innerText = `${gpu.vram_used_mb} MB / ${gpu.vram_total_mb} MB`;
      this.el.vramPercentText.innerText = `${pct}%`;

      if (gpu.vram_warning) {
        this.el.vramBadge.className = 'px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/20 text-rose-400 border border-rose-500/40';
        this.el.vramBadge.innerText = 'PEAK WARNING (>2.5GB)';
        this.el.vramProgress.className = 'h-full bg-rose-500 smooth-progress';
      } else {
        this.el.vramBadge.className = 'px-2 py-0.5 rounded text-[11px] font-semibold bg-cyan-500/20 text-cyan-400 border border-cyan-500/40';
        this.el.vramBadge.innerText = 'DYNAMIC SAFE (<2.5GB)';
        this.el.vramProgress.className = 'h-full bg-cyan-500 smooth-progress';
      }

      if (typeof updateVramChart === 'function') {
        updateVramChart(gpu.vram_used_mb);
      }
    }

    // CPU & RAM
    if (hw && hw.cpu) {
      this.el.cpuPercentText.innerText = `${hw.cpu.percent}%`;
      this.el.cpuProgress.style.width = `${Math.min(hw.cpu.percent, 100)}%`;
    }

    if (hw && hw.ram) {
      this.el.ramUsedText.innerText = `${hw.ram.used_gb} GB (${hw.ram.percent}%)`;
      this.el.ramProgress.style.width = `${Math.min(hw.ram.percent, 100)}%`;
    }

    // MT5 Account
    if (mt5 && mt5.account) {
      const acc = mt5.account;
      this.el.accountBalance.innerText = `$${acc.balance.toFixed(2)}`;
      this.el.accountEquity.innerText = `$${acc.equity.toFixed(2)}`;

      const floating = acc.profit || 0;
      this.el.accountFloatingPnl.innerText = (floating >= 0 ? '+' : '') + `$${floating.toFixed(2)}`;
      this.el.accountFloatingPnl.className = `font-mono text-xs ${floating >= 0 ? 'text-emerald-400' : 'text-rose-400'}`;

      this.el.mt5LoginServer.innerText = `#${acc.login} (${acc.server})`;
      this.el.mt5Ping.innerText = `${mt5.ping_ms || 0} ms`;
    }

    // Active Kill Zones from telemetry
    if (msg.active_kill_zones) {
      this.activeKillZones = msg.active_kill_zones;
    }
  }

  handleTick(tick) {
    if (!tick) return;
    this.latestPrices[tick.symbol] = tick;

    // Update Radar Card for this symbol
    const priceEl = document.getElementById(`price-${tick.symbol}`);
    const spreadEl = document.getElementById(`spread-${tick.symbol}`);
    const badgeEl = document.getElementById(`zone-badge-${tick.symbol}`);
    const cardEl = document.getElementById(`radar-card-${tick.symbol}`);

    if (priceEl) priceEl.innerText = tick.bid.toFixed(tick.symbol.includes('JPY') ? 3 : (tick.symbol.includes('USD') && !tick.symbol.includes('BTC') && !tick.symbol.includes('XAU') ? 5 : 2));
    if (spreadEl) spreadEl.innerText = `${(tick.spread / (tick.symbol.includes('JPY') ? 0.001 : (tick.symbol.includes('EUR') ? 0.00001 : 0.01))).toFixed(0)} pts`;

    // Check if live price is inside Kill Zone
    const zones = this.activeKillZones[tick.symbol] || [];
    let insideZone = null;
    for (const z of zones) {
      if (tick.bid >= z.lower_bound && tick.bid <= z.upper_bound) {
        insideZone = z;
        break;
      }
    }

    if (badgeEl && cardEl) {
      if (insideZone) {
        badgeEl.className = 'px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/50 animate-pulse';
        badgeEl.innerText = `🎯 IN KILL ZONE (${insideZone.direction})`;
        cardEl.classList.add('glass-panel-active');
      } else {
        badgeEl.className = 'px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-400';
        badgeEl.innerText = zones.length > 0 ? `${zones.length} Zones Active` : 'Scanning';
        cardEl.classList.remove('glass-panel-active');
      }
    }

    // Update active position progress if symbol matches
    if (this.activePosition && this.activePosition.symbol === tick.symbol) {
      this.updateActivePositionProgress(tick.bid);
    }
  }

  handleKillZoneUpdate(zone) {
    if (!this.activeKillZones[zone.symbol]) {
      this.activeKillZones[zone.symbol] = [];
    }
    this.activeKillZones[zone.symbol].push(zone);

    window.notifyManager.logActivity(
      `New Kill Zone: ${zone.symbol} ${zone.direction}`,
      `Bounds: [${zone.lower_bound} - ${zone.upper_bound}] Confidence: ${(zone.confidence * 100).toFixed(0)}%`,
      'RADAR',
      'bg-cyan-500/20 text-cyan-300'
    );
  }

  handleTriggerAlert(alert, isBacklog = false) {
    if (!isBacklog) {
      window.notifyManager.playOrderPlaced();
      window.notifyManager.showToast(
        `Sniper Wakeup: ${alert.symbol}`,
        `Detected ${alert.pattern_name} (${alert.direction}) at ${alert.entry_price}. Wick SL: ${alert.wick_sl_price}`,
        'info'
      );
    }
    window.notifyManager.logActivity(
      `Sniper Trigger: ${alert.symbol} ${alert.direction}`,
      `Pattern: ${alert.pattern_name} | Wick SL: ${alert.wick_sl_price} | Conf: ${(alert.model_confidence * 100).toFixed(0)}%`,
      'SNIPER',
      'bg-purple-500/20 text-purple-300'
    );
  }

  handleTradeTicket(ticket) {
    window.notifyManager.logActivity(
      `Risk Guard Approved: ${ticket.symbol}`,
      `Ticket #${ticket.ticket_id} | Lot: 0.01 | Risk: $${ticket.risk_dollars} (<= $2.50) | Win Prob: ${(ticket.win_probability * 100).toFixed(1)}%`,
      'GUARD $50',
      'bg-emerald-500/20 text-emerald-300'
    );
  }

  handleExecution(exec, isBacklog = false) {
    if (exec.status === 'PLACED') {
      this.activePosition = exec;
      this.renderActivePositionCard(exec);
      if (!isBacklog) {
        window.notifyManager.playOrderPlaced();
        window.notifyManager.showToast('🎯 Order Placed', `${exec.direction} 0.01 ${exec.symbol} @ ${exec.fill_price}`, 'success');
      }
    } else if (exec.status === 'MODIFIED_BE') {
      if (this.activePosition) {
        this.activePosition.current_sl = exec.current_sl;
        this.activePosition.be_locked = true;
      }
      this.renderActivePositionCard(this.activePosition || exec);
      if (!isBacklog) {
        window.notifyManager.playBeLocked();
        window.notifyManager.showToast('🛡️ Break-Even Locked!', `${exec.symbol} SL moved to BE +2 pips (${exec.current_sl})`, 'success');
      }
    } else if (exec.status === 'CLOSED') {
      this.activePosition = null;
      this.renderActivePositionCard(null);
      if (!isBacklog) {
        if ((exec.pnl || 0) > 0) {
          window.notifyManager.playTradeProfit();
          window.notifyManager.showToast('💰 Trade Closed in Profit!', `PnL: +$${exec.pnl.toFixed(2)} on ${exec.symbol}`, 'success');
        } else {
          window.notifyManager.showToast('Trade Closed', `PnL: $${exec.pnl.toFixed(2)} on ${exec.symbol}`, 'info');
        }
      }
      this.loadInitialData(); // Refresh history
    }

    window.notifyManager.logActivity(
      `Execution: ${exec.symbol} [${exec.status}]`,
      `Order #${exec.order_id} | Price: ${exec.fill_price} | SL: ${exec.current_sl} | PnL: $${(exec.pnl || 0).toFixed(2)}`,
      'EXEC',
      exec.status === 'MODIFIED_BE' ? 'bg-amber-500/20 text-amber-300' : 'bg-slate-700 text-slate-200'
    );
  }

  handleSystemState(state) {
    if (state.state === 'HALT_TRADING') {
      this.el.redFolderBanner.classList.remove('hidden');
      this.el.redFolderText.innerText = `RED FOLDER HALT ACTIVE: ${state.reason}`;
      window.notifyManager.playAlertWarning();
      window.notifyManager.showToast('🚨 Trading Halted', state.reason, 'danger');
    } else {
      this.el.redFolderBanner.classList.add('hidden');
    }
  }

  renderActivePositionCard(pos) {
    if (!pos) {
      this.el.noActivePositionState.classList.remove('hidden');
      this.el.activePosContent.classList.add('hidden');
      return;
    }

    this.el.noActivePositionState.classList.add('hidden');
    this.el.activePosContent.classList.remove('hidden');

    this.el.activePosSymbol.innerText = pos.symbol;
    this.el.activePosDirection.innerText = pos.direction;
    this.el.activePosDirection.className = `px-2 py-0.5 rounded text-xs font-bold ${pos.direction === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`;
    this.el.activePosEntry.innerText = pos.fill_price;
    this.el.activePosCurrent.innerText = pos.fill_price;
    this.el.activePosSl.innerText = pos.current_sl;

    if (pos.be_locked || pos.status === 'MODIFIED_BE') {
      this.el.activePosBeBadge.className = 'px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/50';
      this.el.activePosBeBadge.innerText = '🛡️ BE +2 PIPS LOCKED (RISK-FREE)';
    } else {
      this.el.activePosBeBadge.className = 'px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-400';
      this.el.activePosBeBadge.innerText = 'Awaiting 1:1.5 R:R Target';
    }
  }

  updateActivePositionProgress(currentPrice) {
    if (!this.activePosition) return;
    this.el.activePosCurrent.innerText = currentPrice;

    const entry = this.activePosition.fill_price;
    const initialSl = this.activePosition.initial_sl;
    const isBuy = this.activePosition.direction === 'BUY';

    const slDistance = Math.abs(entry - initialSl);
    const beDistance = slDistance * 1.5;

    let move = isBuy ? (currentPrice - entry) : (entry - currentPrice);
    let pct = Math.max(0, Math.min(100, (move / (beDistance + 1e-9)) * 100));

    this.el.activePosProgressBar.style.width = `${pct}%`;
  }

  renderRadarCards(zonesData) {
    if (!this.el.radarCardsGrid) return;
    this.el.radarCardsGrid.innerHTML = '';

    const symbols = ['EURUSD', 'USDJPY', 'XAUUSD', 'BTCUSD'];

    symbols.forEach(sym => {
      const data = zonesData[sym] || { zones: [], current_price: null, current_spread: null };
      const card = document.createElement('div');
      card.id = `radar-card-${sym}`;
      card.className = 'glass-panel p-4 flex flex-col justify-between transition-all duration-300';

      const zonesCount = data.zones.length;
      let zonesHtml = '';
      data.zones.slice(0, 2).forEach(z => {
        zonesHtml += `
          <div class="flex items-center justify-between text-[11px] py-1 border-b border-slate-800/60">
            <span class="font-semibold ${z.direction === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}">${z.direction} Zone</span>
            <span class="font-mono text-slate-300">[${z.lower_bound} - ${z.upper_bound}]</span>
          </div>
        `;
      });

      card.innerHTML = `
        <div class="flex items-center justify-between pb-2 border-b border-slate-800">
          <div class="flex items-center gap-2">
            <span class="font-bold text-sm text-slate-100">${sym}</span>
            <span id="spread-${sym}" class="text-[10px] text-slate-400 font-mono">-- pts</span>
          </div>
          <span id="zone-badge-${sym}" class="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-400">
            ${zonesCount > 0 ? `${zonesCount} Zones` : 'Scanning'}
          </span>
        </div>
        <div class="py-3 flex items-baseline justify-between">
          <span class="text-xs text-slate-400">Live Price:</span>
          <span id="price-${sym}" class="font-mono font-bold text-base text-slate-100">${data.current_price || '--'}</span>
        </div>
        <div class="mt-1">
          <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Institutional Kill Zones (M15)</div>
          ${zonesHtml || '<div class="text-[11px] text-slate-500 py-1">Analyzing order flow...</div>'}
        </div>
      `;

      this.el.radarCardsGrid.appendChild(card);
    });
  }

  renderTradesTable(trades) {
    if (!this.el.tradesTableBody) return;
    this.el.tradesTableBody.innerHTML = '';

    if (trades.length === 0) {
      this.el.tradesTableBody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center py-6 text-slate-500 text-xs">No executed trades logged in DuckDB yet.</td>
        </tr>
      `;
      return;
    }

    trades.forEach(t => {
      const isProfit = (t.pnl || 0) >= 0;
      const dateStr = t.entry_timestamp ? new Date(t.entry_timestamp * 1000).toLocaleString() : '--';
      const tr = document.createElement('tr');
      tr.className = 'border-b border-slate-800/80 hover:bg-slate-800/30 text-xs';
      tr.innerHTML = `
        <td class="py-2.5 px-3 font-mono text-slate-300 font-semibold">${t.symbol}</td>
        <td class="py-2.5 px-3">
          <span class="px-1.5 py-0.5 rounded text-[10px] font-bold ${t.direction === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}">
            ${t.direction}
          </span>
        </td>
        <td class="py-2.5 px-3 font-mono text-slate-300">${t.fill_price}</td>
        <td class="py-2.5 px-3 font-mono text-slate-300">${t.exit_price || '--'}</td>
        <td class="py-2.5 px-3 font-mono font-bold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}">
          ${isProfit ? '+' : ''}$${(t.pnl || 0).toFixed(2)}
        </td>
        <td class="py-2.5 px-3 text-slate-400 text-[11px]">${dateStr}</td>
      `;
      this.el.tradesTableBody.appendChild(tr);
    });
  }

  updateSystemStatus(data) {
    if (data.red_folder && data.red_folder.is_active) {
      this.el.redFolderBanner.classList.remove('hidden');
      this.el.redFolderText.innerText = `RED FOLDER HALT ACTIVE: ${data.red_folder.title}`;
    } else {
      this.el.redFolderBanner.classList.add('hidden');
    }
  }

  updateAnalytics(data) {
    if (!data) return;
    if (this.el.winRateText) this.el.winRateText.innerText = `${(data.win_rate_pct || 0).toFixed(1)}%`;
    if (this.el.profitFactorText) this.el.profitFactorText.innerText = `${(data.profit_factor || 0).toFixed(2)}`;
    if (this.el.totalTradesText) this.el.totalTradesText.innerText = `${data.total_trades || 0}`;
    if (this.el.netPnlText) {
      const net = data.net_pnl || 0;
      this.el.netPnlText.innerText = `${net >= 0 ? '+' : ''}$${net.toFixed(2)}`;
      this.el.netPnlText.className = `font-mono text-lg font-bold ${net >= 0 ? 'text-emerald-400' : 'text-rose-400'}`;
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (typeof initVramChart === 'function') {
    initVramChart();
  }
  window.dashboardApp = new DashboardApp();
});
