'use strict';

const { app, BrowserWindow, Tray, Menu, nativeImage, shell } = require('electron');
const path = require('path');
const http = require('http');
const fs = require('fs');
const net = require('net');

let Store;
let store;
let mainWindow;
let tray;
app.isQuitting = false;

async function loadStore() {
  const mod = await import('electron-store');
  Store = mod.default;
  store = new Store({
    name: 'voiceshift-presets',
    defaults: {
      presets: [
        {
          id: 1, name: 'Default', isDefault: true,
          createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
          params: { pitchSemitones: 0, formantShift: 1.0, roboticAmount: 0.0, noiseGateDb: -50, volumeOut: 1.0, highpassFreq: 80, lowpassFreq: 16000, compressorThreshold: -24, compressorRatio: 4 }
        },
        {
          id: 2, name: 'Deep Voice', isDefault: true,
          createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
          params: { pitchSemitones: -4, formantShift: 0.85, roboticAmount: 0.0, noiseGateDb: -45, volumeOut: 1.0, highpassFreq: 60, lowpassFreq: 12000, compressorThreshold: -20, compressorRatio: 5 }
        },
        {
          id: 3, name: 'High Voice', isDefault: true,
          createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
          params: { pitchSemitones: 5, formantShift: 1.2, roboticAmount: 0.0, noiseGateDb: -50, volumeOut: 1.0, highpassFreq: 120, lowpassFreq: 18000, compressorThreshold: -24, compressorRatio: 3 }
        },
        {
          id: 4, name: 'Robot', isDefault: true,
          createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
          params: { pitchSemitones: 2, formantShift: 1.0, roboticAmount: 0.7, noiseGateDb: -50, volumeOut: 1.0, highpassFreq: 80, lowpassFreq: 16000, compressorThreshold: -24, compressorRatio: 4 }
        }
      ],
      nextId: 5
    }
  });
}

function getPresets() { return store.get('presets'); }
function savePresets(presets) { store.set('presets', presets); }
function getNextId() {
  const id = store.get('nextId');
  store.set('nextId', id + 1);
  return id;
}

function findFreePort() {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
  });
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', d => body += d);
    req.on('end', () => {
      try { resolve(body ? JSON.parse(body) : {}); }
      catch (e) { reject(e); }
    });
    req.on('error', reject);
  });
}

const MIME = {
  '.html': 'text/html',
  '.js':   'application/javascript',
  '.mjs':  'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.woff2':'font/woff2',
  '.woff': 'font/woff',
  '.ttf':  'font/ttf',
  '.jpg':  'image/jpeg',
};

function serveStatic(req, res, rendererDir) {
  let urlPath = req.url.split('?')[0];
  if (urlPath === '/') urlPath = '/index.html';
  const filePath = path.join(rendererDir, urlPath);
  const ext = path.extname(filePath);
  const mime = MIME[ext] || 'application/octet-stream';
  fs.readFile(filePath, (err, data) => {
    if (err) {
      // SPA fallback — serve index.html for any unknown route
      fs.readFile(path.join(rendererDir, 'index.html'), (e2, d2) => {
        if (e2) { res.writeHead(404); res.end('Not found'); return; }
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(d2);
      });
      return;
    }
    res.writeHead(200, { 'Content-Type': mime });
    res.end(data);
  });
}

async function startLocalServer(rendererDir) {
  const port = await findFreePort();
  const server = http.createServer(async (req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PATCH,DELETE,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') { res.writeHead(200); res.end(); return; }

    const url = req.url.split('?')[0];

    if (url === '/api/presets' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(getPresets()));
      return;
    }

    if (url === '/api/presets' && req.method === 'POST') {
      try {
        const body = await readBody(req);
        const { name, params } = body;
        if (!name || !params) { res.writeHead(400); res.end(JSON.stringify({ error: 'name and params required' })); return; }
        const preset = {
          id: getNextId(), name, isDefault: false,
          createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
          params
        };
        const presets = getPresets();
        presets.push(preset);
        savePresets(presets);
        res.writeHead(201, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(preset));
      } catch { res.writeHead(400); res.end(JSON.stringify({ error: 'Bad request' })); }
      return;
    }

    const matchGet = url.match(/^\/api\/presets\/(\d+)$/);
    if (matchGet && req.method === 'GET') {
      const id = parseInt(matchGet[1]);
      const presets = getPresets();
      const preset = presets.find(p => p.id === id);
      if (!preset) { res.writeHead(404); res.end(JSON.stringify({ error: 'Not found' })); return; }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(preset));
      return;
    }

    const matchPatch = url.match(/^\/api\/presets\/(\d+)$/);
    if (matchPatch && req.method === 'PATCH') {
      const id = parseInt(matchPatch[1]);
      try {
        const body = await readBody(req);
        const presets = getPresets();
        const idx = presets.findIndex(p => p.id === id);
        if (idx === -1) { res.writeHead(404); res.end(JSON.stringify({ error: 'Not found' })); return; }
        if (body.name !== undefined) presets[idx].name = body.name;
        if (body.params !== undefined) presets[idx].params = { ...presets[idx].params, ...body.params };
        presets[idx].updatedAt = new Date().toISOString();
        savePresets(presets);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(presets[idx]));
      } catch { res.writeHead(400); res.end(JSON.stringify({ error: 'Bad request' })); }
      return;
    }

    if (url.match(/^\/api\/presets\/(\d+)$/) && req.method === 'DELETE') {
      const id = parseInt(url.match(/^\/api\/presets\/(\d+)$/)[1]);
      const presets = getPresets();
      const idx = presets.findIndex(p => p.id === id);
      if (idx === -1) { res.writeHead(404); res.end(JSON.stringify({ error: 'Not found' })); return; }
      presets.splice(idx, 1);
      savePresets(presets);
      res.writeHead(204);
      res.end();
      return;
    }

    serveStatic(req, res, rendererDir);
  });

  server.listen(port, '127.0.0.1');
  return port;
}

// Create a 16x16 purple square tray icon from raw RGBA pixels
function buildTrayIcon() {
  try {
    // 16x16 RGBA: violet #6C63FF
    const size = 16;
    const raw = Buffer.alloc(size * size * 4);
    for (let i = 0; i < size * size; i++) {
      raw[i * 4 + 0] = 108; // R
      raw[i * 4 + 1] = 99;  // G
      raw[i * 4 + 2] = 255; // B
      raw[i * 4 + 3] = 255; // A
    }
    return nativeImage.createFromBuffer(raw, { width: size, height: size });
  } catch {
    return nativeImage.createEmpty();
  }
}

function createTray(win) {
  const icon = buildTrayIcon();
  tray = new Tray(icon);
  tray.setToolTip('VoiceShift — Audio Processor');

  const menu = Menu.buildFromTemplate([
    {
      label: 'Show VoiceShift',
      click: () => {
        win.show();
        win.focus();
      }
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        app.isQuitting = true;
        app.quit();
      }
    }
  ]);
  tray.setContextMenu(menu);

  // Left-click: toggle show/hide
  tray.on('click', () => {
    if (win.isVisible() && !win.isMinimized()) {
      win.hide();
    } else {
      win.show();
      win.focus();
    }
  });
}

async function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    backgroundColor: '#0f0f12',
    title: 'VoiceShift',
    autoHideMenuBar: true,
    show: false, // show after ready-to-show
  });

  // Intercept close: minimize to tray instead of quitting
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  await mainWindow.loadURL(`http://127.0.0.1:${port}`);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  await loadStore();
  const rendererDir = path.join(__dirname, 'renderer');
  const port = await startLocalServer(rendererDir);
  await createWindow(port);
  createTray(mainWindow);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow(port);
    else if (mainWindow) { mainWindow.show(); mainWindow.focus(); }
  });
});

app.on('window-all-closed', () => {
  // Don't quit on all windows closed — tray keeps it alive
  // Only quit when explicitly requested
});

app.on('before-quit', () => {
  app.isQuitting = true;
});
