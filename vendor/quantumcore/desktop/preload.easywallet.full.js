
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('bridge', {
  vault: {
    save: (bytes) => ipcRenderer.invoke('vault:save', bytes),
    get: () => ipcRenderer.invoke('vault:get'),
    del: () => ipcRenderer.invoke('vault:del')
  },
  wallet: {
    derive: (index) => ipcRenderer.invoke('wallet:derive', index),
    evmSend: (payload, env) => ipcRenderer.invoke('wallet:evm:send', payload, env),
    btcSend: (payload, env) => ipcRenderer.invoke('wallet:btc:send', payload, env),
    cosmosSend: (payload, env) => ipcRenderer.invoke('wallet:cosmos:send', payload, env),
    dagInfo: () => ipcRenderer.invoke('wallet:dag:info')
  }
})
