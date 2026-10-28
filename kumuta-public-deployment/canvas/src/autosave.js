// One writer per mounted board. Changes during a request coalesce into the next
// request; errors stop the queue, including ambiguous network failures.
export class Autosave {
  constructor({ revision, scene, save, onState = () => {}, delay = 1000 }) {
    Object.assign(this, { revision, save, onState, delay });
    this.latest = scene; this.saved = JSON.stringify(scene); this.error = null;
    this.running = null; this.timer = null; this.disposed = false;
  }
  get dirty() { return JSON.stringify(this.latest) !== this.saved; }
  report(status, error = null) {
    const next = { status, error, revision: this.revision, dirty: this.dirty };
    if (this.disposed || (this.lastState && Object.keys(next).every(k => next[k] === this.lastState[k]))) return;
    this.lastState = next; this.onState(next);
  }
  change(scene) {
    this.latest = scene; clearTimeout(this.timer);
    if (this.error) { this.report(this.error.status === 409 ? 'conflict' : 'error', this.error); return; }
    if (!this.dirty) { this.report(this.running ? 'saving' : 'saved'); return; }
    this.report('pending');
    this.timer = setTimeout(() => this.flush().catch(() => {}), this.delay);
  }
  async flush() {
    clearTimeout(this.timer);
    if (this.error) throw this.error;
    if (this.running) { await this.running; return this.flush(); }
    if (!this.dirty || this.disposed) return;
    const scene = this.latest, fingerprint = JSON.stringify(scene);
    this.report('saving');
    this.running = (async () => {
      try {
        const result = await this.save(scene, this.revision);
        this.revision = result.revision; this.saved = fingerprint;
      } catch (error) {
        this.error = error;
        this.report(error.status === 409 ? 'conflict' : 'error', error);
        throw error;
      } finally { this.running = null; }
    })();
    await this.running;
    if (this.disposed) return;
    if (this.dirty) return this.flush();
    this.report('saved');
  }
  retry() { if (this.error?.status === 409) return Promise.reject(this.error); this.error = null; return this.flush(); }
  dispose() { this.disposed = true; clearTimeout(this.timer); }
}
