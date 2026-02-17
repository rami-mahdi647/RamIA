(function () {
  const state = {
    mode: 'guided',
    apiBase: localStorage.getItem('coreui.apiBase') || '/api'
  };

  const output = document.getElementById('output');
  const statusBadge = document.getElementById('status-badge');
  const guidedPanel = document.getElementById('guided-panel');
  const advancedPanel = document.getElementById('advanced-panel');

  const endpoints = {
    status: '/status',
    walletCreate: '/wallet_create',
    walletInfo: '/wallet_info',
    mine: '/mine',
    send: '/send',
    guardianExplain: '/guardian_explain',
    mempoolList: '/mempool_list',
    txList: '/tx_list',
    blocksLatest: '/blocks_latest',
    blockGet: '/block_get'
  };

  function setBadge(kind, text) {
    statusBadge.className = `badge ${kind}`;
    statusBadge.textContent = text;
  }

  function writeOutput(data) {
    output.textContent = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
  }

  function fullPath(path) {
    const base = (state.apiBase || '/api').replace(/\/$/, '');
    return `${base}${path}`;
  }

  async function post(path, payload) {
    const url = fullPath(path);
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {})
      });
      const data = await res.json();
      if (res.ok && data.ok !== false) {
        setBadge('ok', 'Success');
      } else {
        setBadge('error', 'Failed');
      }
      writeOutput({ endpoint: url, response: data });
      return data;
    } catch (err) {
      setBadge('error', 'Request error');
      writeOutput({ endpoint: url, error: String(err) });
      return null;
    }
  }

  function guidedSendPayload() {
    return {
      from_addr: document.getElementById('guided-from').value,
      to_addr: document.getElementById('guided-to').value,
      amount: Number(document.getElementById('guided-amount').value || 0),
      fee: Number(document.getElementById('guided-fee').value || 0),
      memo: document.getElementById('guided-memo').value
    };
  }

  async function runAction(action) {
    switch (action) {
      case 'status':
        return post(endpoints.status, {});
      case 'walletCreate':
        return post(endpoints.walletCreate, { label: 'default' });
      case 'walletInfo':
        return post(endpoints.walletInfo, {});
      case 'mine':
        return post(endpoints.mine, { any_miner_addr: 'x' });
      case 'send':
        return post(endpoints.send, guidedSendPayload());
      case 'guardianExplain': {
        const txid = (document.getElementById('guided-txid').value || '').trim();
        return post(endpoints.guardianExplain, { txid });
      }
      case 'mempoolList':
        return post(endpoints.mempoolList, {});
      case 'txList':
        return post(endpoints.txList, {});
      case 'blocksLatest':
        return post(endpoints.blocksLatest, { limit: 10 });
      case 'blockGet': {
        const hash = (document.getElementById('guided-block-hash').value || '').trim();
        return post(endpoints.blockGet, { block_hash: hash });
      }
      case 'saveSettings': {
        const nextBase = (document.getElementById('api-base').value || '/api').trim();
        state.apiBase = nextBase;
        localStorage.setItem('coreui.apiBase', nextBase);
        setBadge('ok', 'Settings saved');
        writeOutput({ ok: true, apiBase: nextBase });
        return;
      }
      default:
        setBadge('error', 'Unknown action');
        writeOutput(`Unknown action: ${action}`);
    }
  }

  function setMode(mode) {
    state.mode = mode;
    document.querySelectorAll('.mode-toggle button').forEach((btn) => {
      const active = btn.dataset.mode === mode;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-selected', String(active));
    });
    guidedPanel.classList.toggle('hidden', mode !== 'guided');
    advancedPanel.classList.toggle('hidden', mode !== 'advanced');
  }

  function setTab(tabName) {
    document.querySelectorAll('.tab').forEach((tab) => {
      tab.classList.toggle('is-active', tab.dataset.tab === tabName);
    });
    document.querySelectorAll('.tab-panel').forEach((panel) => {
      panel.classList.toggle('is-active', panel.dataset.panel === tabName);
    });
  }

  document.addEventListener('click', (event) => {
    const modeButton = event.target.closest('[data-mode]');
    if (modeButton) {
      setMode(modeButton.dataset.mode);
      return;
    }

    const tabButton = event.target.closest('.tab');
    if (tabButton) {
      setTab(tabButton.dataset.tab);
      return;
    }

    const actionButton = event.target.closest('[data-action]');
    if (actionButton) {
      runAction(actionButton.dataset.action);
    }
  });

  document.getElementById('api-base').value = state.apiBase;
  setMode('guided');
  setTab('wallet');
})();
