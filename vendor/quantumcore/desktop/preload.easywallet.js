const { contextBridge, ipcRenderer } = require('electron')
contextBridge.exposeInMainWorld('bridge', {
  vault: {
    save: (bytes) => ipcRenderer.invoke('vault:save', bytes),
    get: () => ipcRenderer.invoke('vault:get'),
    del: () => ipcRenderer.invoke('vault:del')
  }
})
