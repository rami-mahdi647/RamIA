const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('api', {
  fetchJSON: (url) => ipcRenderer.invoke('fetch-json', url)
});
