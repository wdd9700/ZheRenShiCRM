'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('acceptance', Object.freeze({ seed: () => ipcRenderer.invoke('acceptance:seed'), report: snapshot => ipcRenderer.invoke('acceptance:report', snapshot) }));
