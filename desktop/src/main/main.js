// Electron main process: starts the Python backend, waits for it, opens the window.
const { systemPreferences, app, BrowserWindow, ipcMain, dialog, session, safeStorage } = require('electron');
const { spawn } = require('child_process');
const crypto = require('crypto');
const path = require('path');
const fs = require('fs');
const { pathToFileURL } = require('url');

const ROOT = path.join(__dirname, '..', '..');
const TOKEN = crypto.randomBytes(24).toString('hex');
const RENDERER = path.join(ROOT, 'src', 'renderer', 'index.html');
const RENDERER_URL = pathToFileURL(RENDERER).href;
let backend = null;
let baseUrl = null;
const ICON = path.join(__dirname, '..', '..', 'assets', 'icon.png');   // the Selfbrowse mark; packaged builds use assets/icon.icns
let quitting = false;

function pythonPath() {
  const venv = path.join(ROOT, 'backend', '.venv', 'bin', 'python');
  if (fs.existsSync(venv)) return venv;
  throw new Error('Backend not set up. Run "npm run backend:setup" in the desktop folder.');
}

// From source: the venv's Python runs backend/server.py. Packaged: the frozen backend shipped inside the app.
function backendCommand() {
  if (app.isPackaged) {
    const exe = path.join(process.resourcesPath, 'backend', 'selfbrowse-backend');
    if (!fs.existsSync(exe)) throw new Error('This copy of Selfbrowse is missing its backend. Reinstall it.');
    return [exe, []];
  }
  return [pythonPath(), [path.join(ROOT, 'backend', 'server.py')]];
}

function startBackend() {
  return new Promise((resolve, reject) => {
    const [cmd, args] = backendCommand();
    backend = spawn(cmd, args, {
      env: { ...process.env, SB_DESKTOP_TOKEN: TOKEN, SB_DESKTOP_DATA: app.getPath('userData') },
    });
    let buf = '';
    backend.stdout.on('data', (d) => {
      buf += d.toString();
      const m = buf.match(/READY (\d+)/);
      if (m) resolve(`http://127.0.0.1:${m[1]}`);
    });
    backend.stderr.on('data', (d) => process.stderr.write(d));
    backend.on('exit', (code) => {
      if (!baseUrl) return reject(new Error(`backend exited (${code}) before it was ready`));
      if (!quitting) {                                   // it died while the app was open: do not leave a dead window
        dialog.showErrorBox('Selfbrowse stopped', `The backend exited unexpectedly (${code}).`);
        app.quit();
      }
    });
    setTimeout(() => reject(new Error('backend did not start within 30 seconds')), 30000);
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1360, height: 860, minWidth: 1100, minHeight: 640, title: 'Selfbrowse', icon: ICON,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true,
      allowRunningInsecureContent: false, webviewTag: false,
    },
  });
  // The window only ever shows our own page. Anything else (a link, a redirect, window.open) is refused.
  win.webContents.on('will-navigate', (e) => e.preventDefault());
  win.webContents.on('will-redirect', (e) => e.preventDefault());
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.loadFile(RENDERER);
}

// Hand the token only to our own page, never to another frame or URL.
ipcMain.handle('backend', (event) => {
  own(event);
  return { baseUrl, token: TOKEN };
});

function own(event) {                                   // only our own page may use these
  if (event.senderFrame.url !== RENDERER_URL) throw new Error('not allowed');
}

// "My info" is encrypted with the operating system's keychain (Keychain on macOS, DPAPI on Windows, a
// secret service on Linux). It is never written as plain text, never sent anywhere, and not put in shared flows.
const VAULT = () => path.join(app.getPath('userData'), 'my-info.bin');
const MAX_VAULT = 256 * 1024;

ipcMain.handle('vault:load', (event) => {
  own(event);
  if (!fs.existsSync(VAULT())) return { forms: [] };
  if (!safeStorage.isEncryptionAvailable()) throw new Error('Secure storage is not available on this computer.');
  return JSON.parse(safeStorage.decryptString(fs.readFileSync(VAULT())));
});

ipcMain.handle('vault:save', (event, data) => {
  own(event);
  if (!safeStorage.isEncryptionAvailable()) throw new Error('Secure storage is not available, so nothing was saved.');
  const text = JSON.stringify(data);
  if (typeof text !== 'string' || text.length > MAX_VAULT) throw new Error('That is too much to store.');
  fs.writeFileSync(VAULT(), safeStorage.encryptString(text), { mode: 0o600 });
  return true;
});

// Showing a saved password asks the operating system to confirm it is you (Touch ID on a Mac that has it).
// Where there is no such prompt, a plain confirmation is the best that can be done, and the app says so.
ipcMain.handle('auth:confirm', async (event, reason) => {
  own(event);
  const why = String(reason || 'show a saved password').slice(0, 80);
  if (process.platform === 'darwin' && systemPreferences.canPromptTouchID()) {
    try { await systemPreferences.promptTouchID(why); return { ok: true, strong: true }; } catch (_) { return { ok: false, strong: true }; }
  }
  const win = BrowserWindow.fromWebContents(event.sender);
  const { response } = await dialog.showMessageBox(win, { type: 'question', buttons: ['Show', 'Cancel'], defaultId: 1, cancelId: 1,
    message: `Selfbrowse wants to ${why}.`, detail: 'This computer has no fingerprint or password prompt to use here, so this is only a confirmation.' });
  return { ok: response === 0, strong: false };
});

// Model sources and their API keys: encrypted the same way as My info.
const MODELS = () => path.join(app.getPath('userData'), 'models.bin');
ipcMain.handle('models:load', (event) => {
  own(event);
  if (!fs.existsSync(MODELS())) return null;
  if (!safeStorage.isEncryptionAvailable()) throw new Error('Secure storage is not available on this computer.');
  return JSON.parse(safeStorage.decryptString(fs.readFileSync(MODELS())));
});
ipcMain.handle('models:save', (event, data) => {
  own(event);
  if (!safeStorage.isEncryptionAvailable()) throw new Error('Secure storage is not available, so nothing was saved.');
  const text = JSON.stringify(data);
  if (typeof text !== 'string' || text.length > 256 * 1024) throw new Error('That is too much to store.');
  fs.writeFileSync(MODELS(), safeStorage.encryptString(text), { mode: 0o600 });
  return true;
});

// Saving a shared flow: the person picks the place in the system dialog.
ipcMain.handle('save-file', async (event, name, text) => {
  own(event);
  if (typeof text !== 'string' || text.length > 2 * 1024 * 1024) throw new Error('That file is too large.');
  const safe = String(name || 'flow').replace(/[^A-Za-z0-9._ -]/g, '_').slice(0, 80) || 'flow';
  const win = BrowserWindow.fromWebContents(event.sender);
  const r = await dialog.showSaveDialog(win, { defaultPath: safe, filters: [{ name: 'Selfbrowse flow', extensions: ['json'] }] });
  if (r.canceled || !r.filePath) return null;
  fs.writeFileSync(r.filePath, text, { mode: 0o600 });
  return r.filePath;
});

if (!app.requestSingleInstanceLock()) app.quit();    // a second copy would start a second backend

app.whenReady().then(async () => {
  if (process.platform === 'darwin' && app.dock) app.dock.setIcon(ICON);
  session.defaultSession.setPermissionRequestHandler((_wc, _perm, cb) => cb(false));   // no camera, mic, location...
  session.defaultSession.setPermissionCheckHandler(() => false);
  try {
    baseUrl = await startBackend();
    createWindow();
  } catch (err) {
    dialog.showErrorBox('Selfbrowse could not start', String(err.message || err));
    app.quit();
  }
});

app.on('window-all-closed', () => app.quit());
let closingSessions = false;
app.on('before-quit', async (event) => {
  quitting = true;
  if (closingSessions || !baseUrl) return;
  event.preventDefault();                       // close the browsers kept for follow-ups first, so no Chrome is left behind
  closingSessions = true;
  try { await fetch(`${baseUrl}/sessions/close`, { method: 'POST', headers: { Authorization: `Bearer ${TOKEN}` }, signal: AbortSignal.timeout(4000) }); } catch (_) { /* quit anyway */ }
  app.quit();
});
app.on('quit', () => { if (backend) backend.kill(); });
