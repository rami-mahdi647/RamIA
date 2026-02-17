const { contextBridge } = require('electron');
contextBridge.exposeInMainWorld('quantumcore', { version: '1.0.0' });
