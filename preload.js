const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  closeApp: () => ipcRenderer.send('close-app'),
  selectDirectory: () => ipcRenderer.invoke('select-directory'),
  onBackendLog: (callback) => ipcRenderer.on('backend-log', (_event, value) => callback(value)),
  openExternal: (url) => ipcRenderer.invoke('open-external', url)
});

