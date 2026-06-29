'use strict';
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('__ELECTRON__', {
  version: process.versions.electron,
});
