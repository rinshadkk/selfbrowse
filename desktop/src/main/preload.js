const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('selfbrowse', {
  backend: () => ipcRenderer.invoke('backend'),
  loadMyInfo: () => ipcRenderer.invoke('vault:load'),
  saveMyInfo: (data) => ipcRenderer.invoke('vault:save', data),
  confirmIdentity: (reason) => ipcRenderer.invoke('auth:confirm', reason),
  loadModels: () => ipcRenderer.invoke('models:load'),
  saveModels: (data) => ipcRenderer.invoke('models:save', data),
  saveFile: (name, text) => ipcRenderer.invoke('save-file', name, text),
});
