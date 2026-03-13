const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let store;
let pythonProcess;

ipcMain.handle('set-api-key', (event, { provider, apiKey }) => {
  if (store) {
    store.set(`apiKeys.${provider}`, apiKey);
  }
});

ipcMain.handle('get-api-key', (event, provider) => {
  if (store) {
    return store.get(`apiKeys.${provider}`);
  }
});

ipcMain.handle('select-directory', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory']
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('open-external', async (_event, url) => {
  if (url && url.startsWith('http')) {
    await shell.openExternal(url);
  }
});

let mainWindow;

function startPythonBackend() {
  const scriptPath = path.join(__dirname, 'backend', 'server.py');
  pythonProcess = spawn('python', [scriptPath]);

  function sendToRenderer(data) {
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('backend-log', data.toString());
    }
  }

  pythonProcess.stdout.on('data', (data) => {
    const str = data.toString();
    console.log(`Python: ${str}`);
    sendToRenderer(str);
  });

  pythonProcess.stderr.on('data', (data) => {
    const str = data.toString();
    console.error(`Python Error: ${str}`);
    sendToRenderer(str);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    title: 'Easy Company',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js')
    }
  });

  mainWindow.setMenu(null);
  mainWindow.loadFile('canvas.html');
}

app.whenReady().then(async () => {
  const { default: Store } = await import('electron-store');
  store = new Store();
  console.log("API Keys are saved at:", store.path);
  startPythonBackend();

  createWindow();

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit();
});

app.on('will-quit', () => {
  if (pythonProcess) pythonProcess.kill();
});

ipcMain.on('close-app', () => {
  app.quit();
});
