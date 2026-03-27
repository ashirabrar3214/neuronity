const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let pythonProcess;

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
  const scriptPath = path.join(__dirname, 'backend', 'interpreter.py');
  pythonProcess = spawn('python', [scriptPath], {
    env: { ...process.env, PYTHONUTF8: '1' }
  });

  function sendToRenderer(data) {
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('backend-log', data.toString());
    }
  }

  pythonProcess.stdout.on('data', (data) => {
    const str = data.toString();
    console.log(`Python: ${str.trim()}`);
    sendToRenderer(str);
  });

  pythonProcess.stderr.on('data', (data) => {
    const str = data.toString();
    // Only prefix as Error if it doesn't look like a standard Uvicorn INFO/WARNING log
    if (str.includes('INFO:') || str.includes('WARNING:')) {
      console.log(`Python backend: ${str.trim()}`);
    } else {
      console.error(`Python backend Error: ${str.trim()}`);
    }
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
