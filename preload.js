const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  closeApp: () => ipcRenderer.send('close-app'),
  setApiKey: (args) => ipcRenderer.invoke('set-api-key', args),
  getApiKey: (provider) => ipcRenderer.invoke('get-api-key', provider),
  selectDirectory: () => ipcRenderer.invoke('select-directory'),
  onBackendLog: (callback) => ipcRenderer.on('backend-log', (_event, value) => callback(value)),
  openExternal: (url) => ipcRenderer.invoke('open-external', url)
});

