/**
 * In-Browser Audio Synthesizer and Toast Notification Manager.
 * Uses Web Audio API for zero-dependency sound chimes.
 */
class NotificationManager {
  constructor() {
    this.soundEnabled = localStorage.getItem('sound_enabled') !== 'false';
    this.audioCtx = null;
    this.toastContainer = null;
    this.eventListContainer = null;
    this.initAudioContext();
  }

  initAudioContext() {
    // AudioContext will be initialized or resumed on user gesture
    const initOrResume = () => {
      if (!this.audioCtx) {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (AudioContext) {
          this.audioCtx = new AudioContext();
        }
      } else if (this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }
    };
    window.addEventListener('click', initOrResume, { once: true });
    window.addEventListener('touchstart', initOrResume, { once: true });
  }

  toggleSound() {
    this.soundEnabled = !this.soundEnabled;
    localStorage.setItem('sound_enabled', this.soundEnabled ? 'true' : 'false');
    if (this.soundEnabled && this.audioCtx && this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }
    return this.soundEnabled;
  }

  playTone(freq, type = 'sine', duration = 0.15, startTime = 0) {
    if (!this.soundEnabled || !this.audioCtx) return;
    try {
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();

      osc.type = type;
      osc.frequency.setValueAtTime(freq, this.audioCtx.currentTime + startTime);

      gain.gain.setValueAtTime(0.12, this.audioCtx.currentTime + startTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + startTime + duration);

      osc.connect(gain);
      gain.connect(this.audioCtx.destination);

      osc.start(this.audioCtx.currentTime + startTime);
      osc.stop(this.audioCtx.currentTime + startTime + duration);
    } catch (e) {
      console.debug('Audio play tone error:', e);
    }
  }

  playOrderPlaced() {
    // 2-tone chime: C5 (523Hz) -> G5 (784Hz)
    this.playTone(523.25, 'sine', 0.18, 0);
    this.playTone(783.99, 'sine', 0.25, 0.12);
  }

  playBeLocked() {
    // Ascending victory chime: E5 (659Hz) -> G5 (784Hz) -> C6 (1046Hz)
    this.playTone(659.25, 'triangle', 0.15, 0);
    this.playTone(783.99, 'triangle', 0.15, 0.10);
    this.playTone(1046.50, 'sine', 0.35, 0.20);
  }

  playAlertWarning() {
    // Warning pulse
    this.playTone(440, 'sawtooth', 0.15, 0);
    this.playTone(349, 'sawtooth', 0.25, 0.12);
  }

  playTradeProfit() {
    this.playTone(587.33, 'sine', 0.15, 0);
    this.playTone(880.00, 'sine', 0.35, 0.12);
  }

  showToast(title, message, type = 'info', duration = 5000) {
    if (!this.toastContainer) {
      this.toastContainer = document.getElementById('toast-container');
    }
    if (!this.toastContainer) return;

    const colors = {
      success: {
        border: 'border-emerald-500/60',
        bg: 'bg-emerald-950/80',
        badge: 'bg-emerald-500/20 text-emerald-400',
        icon: '✓'
      },
      info: {
        border: 'border-cyan-500/60',
        bg: 'bg-slate-900/90',
        badge: 'bg-cyan-500/20 text-cyan-400',
        icon: 'ℹ'
      },
      warning: {
        border: 'border-amber-500/60',
        bg: 'bg-amber-950/80',
        badge: 'bg-amber-500/20 text-amber-400',
        icon: '⚠'
      },
      danger: {
        border: 'border-rose-500/60',
        bg: 'bg-rose-950/80',
        badge: 'bg-rose-500/20 text-rose-400',
        icon: '✕'
      }
    };

    const scheme = colors[type] || colors.info;

    const toast = document.createElement('div');
    toast.className = `toast-item glass-panel ${scheme.bg} ${scheme.border} border p-4 shadow-xl max-w-sm flex items-start gap-3 backdrop-blur-lg`;
    toast.innerHTML = `
      <div class="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm shrink-0 ${scheme.badge}">
        ${scheme.icon}
      </div>
      <div class="flex-1 min-w-0">
        <h4 class="font-semibold text-sm text-slate-100">${title}</h4>
        <p class="text-xs text-slate-300 mt-0.5 leading-relaxed break-words">${message}</p>
        <span class="text-[10px] text-slate-400 mt-1 block">${new Date().toLocaleTimeString()}</span>
      </div>
      <button class="text-slate-400 hover:text-slate-200 text-xs px-1 close-btn">✕</button>
    `;

    this.toastContainer.appendChild(toast);

    // Trigger animation
    requestAnimationFrame(() => {
      toast.classList.add('show');
    });

    const closeToast = () => {
      toast.classList.remove('show');
      toast.classList.add('hide');
      setTimeout(() => toast.remove(), 300);
    };

    toast.querySelector('.close-btn').addEventListener('click', closeToast);

    if (duration > 0) {
      setTimeout(closeToast, duration);
    }
  }

  logActivity(title, detail, badge = 'INFO', badgeColor = 'bg-slate-800 text-slate-300') {
    if (!this.eventListContainer) {
      this.eventListContainer = document.getElementById('activity-log-feed');
    }
    if (!this.eventListContainer) return;

    const timeStr = new Date().toLocaleTimeString();
    const item = document.createElement('div');
    item.className = 'py-2.5 px-3 rounded-lg bg-slate-900/60 border border-slate-800/80 flex items-start justify-between gap-3 text-xs';
    item.innerHTML = `
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2">
          <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${badgeColor}">${badge}</span>
          <span class="font-medium text-slate-200 truncate">${title}</span>
        </div>
        <p class="text-slate-400 text-[11px] mt-1 break-words">${detail}</p>
      </div>
      <span class="text-[10px] text-slate-400 shrink-0 font-mono">${timeStr}</span>
    `;

    this.eventListContainer.insertBefore(item, this.eventListContainer.firstChild);

    // Keep log max 50 items
    if (this.eventListContainer.children.length > 50) {
      this.eventListContainer.removeChild(this.eventListContainer.lastChild);
    }
  }
}

window.notifyManager = new NotificationManager();
