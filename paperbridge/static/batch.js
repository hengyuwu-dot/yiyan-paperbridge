/* A durable list of independent jobs; the server runs their inference sequentially. */
(function(root) {
  const processing = status => ['queued', 'running', 'exporting'].includes(status);
  const retryable = status => ['ready', 'failed', 'interrupted', 'cancelled'].includes(status);
  class BatchQueue {
    constructor(storage) {
      this.storage = storage;
      try { this.items = JSON.parse(storage.getItem('paperbridge.batch') || '[]'); }
      catch { this.items = []; }
      if (!Array.isArray(this.items)) this.items = [];
      this.items = this.items.filter(item => /^[a-f0-9]{32}$/.test(item.id));
    }
    save() { this.storage.setItem('paperbridge.batch', JSON.stringify(this.items)); }
    add(document) {
      const existing = this.items.find(item => item.id === document.id);
      if (!existing) this.items.push({id:document.id, name:document.name, status:document.status, progress:document.progress,pages:document.settings?.pages || ''});
      else this.update(document);
      this.save();
    }
    update(document) {
      const item = this.items.find(item => item.id === document.id);
      if (item) {
        if (document.status !== item.status || processing(document.status) || document.status === 'complete') delete item.error;
        Object.assign(item, {name:document.name,status:document.status,progress:document.progress,pages:document.settings?.pages || ''});
        this.save();
      }
    }
    async refresh(fetchDocument) {
      // The list can be cleared or extended while a status request is pending.
      // Apply replies by ID, rather than by a now-stale array position.
      const ids = this.items.map(item => item.id);
      const replies = await Promise.allSettled(ids.map(fetchDocument));
      replies.forEach((reply, i) => {
        const item = this.items.find(entry => entry.id === ids[i]);
        if (!item) return;
        if (reply.status === 'fulfilled') {
          delete item.fetchError;
          this.update(reply.value);
        } else item.fetchError = reply.reason?.message || '论文状态暂时无法读取';
      });
      this.save();
    }
    async start(settings, submit, onChange) {
      // Snapshot before any asynchronous step: selecting another paper cannot
      // change the settings of subsequent entries in this submission.
      const chosen = JSON.parse(JSON.stringify(settings));
      const pending = this.items.filter(item => retryable(item.status));
      for (const item of pending) {
        delete item.error;
        try { this.update(await submit(item.id, chosen)); }
        catch(error) { item.error = error.message; this.save(); }
        onChange();
      }
    }
    remove(id) {
      const item = this.items.find(entry => entry.id === id);
      if(!item || processing(item.status)) return false;
      this.items = this.items.filter(entry => entry.id !== id); this.save(); return true;
    }
    clear() { this.items = []; this.save(); }
  }
  root.PaperBatch = {BatchQueue, processing, retryable};
  if (typeof module !== 'undefined') module.exports = {BatchQueue, processing, retryable};
})(typeof window === 'undefined' ? globalThis : window);
