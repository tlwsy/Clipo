let database;
function open() {
  if (!database)
    database = new Promise((resolve, reject) => {
      const request = indexedDB.open("clipo-extension", 1);
      request.onupgradeneeded = () =>
        request.result.createObjectStore("pending", { keyPath: "id" });
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => {
        database = undefined;
        reject(new Error("无法打开本机保存队列"));
      };
    });
  return database;
}
async function transaction(mode, action) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("pending", mode);
    const query = action(tx.objectStore("pending"));
    tx.oncomplete = () => resolve(query?.result);
    tx.onabort = tx.onerror = () =>
      reject(new Error("无法写入本机保存队列，请检查磁盘空间"));
  });
}
export const pending = () => transaction("readonly", (store) => store.getAll());
export const save = (item) =>
  transaction("readwrite", (store) => store.put(item));
export const remove = (id) =>
  transaction("readwrite", (store) => store.delete(id));
export const clear = () => transaction("readwrite", (store) => store.clear());
