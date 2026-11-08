'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('desktop', Object.freeze({
  readSettings: () => ipcRenderer.invoke('settings:read'),
  saveSettings: connection => ipcRenderer.invoke('settings:save', connection),
  connect: () => ipcRenderer.invoke('connection:open'),
  updateStatus: () => ipcRenderer.invoke('update:status'),
  checkUpdate: () => ipcRenderer.invoke('update:check'),
  downloadUpdate: () => ipcRenderer.invoke('update:download'),
  installUpdate: () => ipcRenderer.invoke('update:install')
}));
