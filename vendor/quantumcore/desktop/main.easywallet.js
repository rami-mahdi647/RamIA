const { app, BrowserWindow, ipcMain, shell } = require('electron')
const path = require('path')
const keytar = require('keytar')
const SERVICE = 'QuantumCore'
const ACCOUNT = 'default-seed'

function createWindow(){
  const win = new BrowserWindow({
    width: 1280, height: 860,
    webPreferences: { preload: path.join(__dirname, 'preload.easywallet.js'), contextIsolation: true, nodeIntegration: false, sandbox: true }
  })
  win.loadFile(path.join(__dirname, 'app', 'index.html'))
  win.webContents.setWindowOpenHandler(({url}) => { shell.openExternal(url); return { action: 'deny' } })
}

app.whenReady().then(()=>{
  // Vault IPC
  ipcMain.handle('vault:save', async (_e, bytes) => {
    const buf = Buffer.from(Uint8Array.from(bytes))
    await keytar.setPassword(SERVICE, ACCOUNT, buf.toString('base64'))
    return true
  })
  ipcMain.handle('vault:get', async ()=> {
    const b64 = await keytar.getPassword(SERVICE, ACCOUNT)
    if (!b64) return null
    const buf = Buffer.from(b64, 'base64')
    return Array.from(buf)
  })
  ipcMain.handle('vault:del', async ()=> {
    await keytar.deletePassword(SERVICE, ACCOUNT)
    return true
  })

  createWindow()
})

app.on('window-all-closed', ()=>{ if (process.platform !== 'darwin') app.quit() })
app.on('activate', ()=>{ if (BrowserWindow.getAllWindows().length === 0) createWindow() })
