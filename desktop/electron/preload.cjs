const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld(
  "campus",
  Object.freeze({
    request: (path, method = "GET", body) =>
      ipcRenderer.invoke("api:request", { path, method, body }),
    profiles: () => ipcRenderer.invoke("profiles:list"),
    createProfile: (name) => ipcRenderer.invoke("profiles:create", name),
    selectProfile: (id) => ipcRenderer.invoke("profiles:select", id),
    chooseJson: (kind) => ipcRenderer.invoke("files:json", kind),
    upload: (parentId) => ipcRenderer.invoke("files:upload", parentId),
    connect: (service) => ipcRenderer.invoke("google:connect", service),
    configureSummary: () => ipcRenderer.invoke("summary:configure"),
    download: (id) => ipcRenderer.invoke("files:download", id),
    openUrl: (url) => ipcRenderer.invoke("links:open", url),
  }),
);
