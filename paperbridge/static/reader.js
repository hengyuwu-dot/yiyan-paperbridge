/* Two document panes share page navigation with independent zoom and optional scroll synchronization. */
(function (root) {
  function fraction(position, extent) {
    return extent > 0 ? Math.max(0, Math.min(1, position / extent)) : 0;
  }
  function documentTerms(settings, saved, newDocument) {
    return !newDocument && typeof settings.glossary === 'string' ? settings.glossary : saved;
  }
  class SynchronizedReader {
    constructor(panes, papers, toggle, zoom, sideZooms = [], zoomLink = null) {
      this.panes = panes;
      this.papers = papers;
      this.enabled = toggle.checked;
      this.expected = new WeakMap();
      this.scales = panes.map(() => Number(zoom.value));
      this.sideZooms = sideZooms;
      this.zoomControl = zoom;
      this.zoomLink = zoomLink;
      panes.forEach(pane => pane.addEventListener('scroll', () => this.scrolled(pane), {passive: true}));
      toggle.addEventListener('change', () => {
        this.enabled = toggle.checked;
        if (this.enabled) this.mirror(this.active || panes[0]);
      });
      zoom.addEventListener('change', () => {
        this.setZoom(0, Number(zoom.value), true);
      });
      sideZooms.forEach((control, index) => control.addEventListener('change', () => {
        this.setZoom(index, Number(control.value), !!zoomLink?.checked);
      }));
      zoomLink?.addEventListener('change', () => {
        if (zoomLink.checked) this.setZoom(this.panes.indexOf(this.active || panes[0]),
          this.scales[this.panes.indexOf(this.active || panes[0])], true);
      });
      this.observer = new ResizeObserver(() => this.resize());
      panes.forEach(pane => this.observer.observe(pane));
      papers.forEach(paper => paper.querySelector('img').addEventListener('load', () => this.resize()));
    }
    scrolled(pane) {
      const target = this.expected.get(pane);
      if (target && Math.abs(pane.scrollTop - target.top) < 1 && Math.abs(pane.scrollLeft - target.left) < 1) {
        this.expected.delete(pane);
        return;
      }
      this.expected.delete(pane);
      this.active = pane;
      if (this.enabled) this.mirror(pane);
    }
    mirror(source) {
      const y = fraction(source.scrollTop, source.scrollHeight - source.clientHeight);
      const x = fraction(source.scrollLeft, source.scrollWidth - source.clientWidth);
      this.panes.filter(pane => pane !== source).forEach(pane => {
        const top = y * Math.max(0, pane.scrollHeight - pane.clientHeight);
        const left = x * Math.max(0, pane.scrollWidth - pane.clientWidth);
        this.expected.set(pane, {top, left});
        pane.scrollTop = top;
        pane.scrollLeft = left;
      });
    }
    setZoom(index, value, linked = false) {
      if (!Number.isFinite(value) || value < 50 || value > 400) return;
      if (linked) this.scales.fill(value);
      else this.scales[index] = value;
      this.sideZooms.forEach((control, i) => { control.value = String(this.scales[i]); });
      this.zoomControl.value = this.scales.every(scale => scale === this.scales[0]) ? String(this.scales[0]) : '';
      this.resize();
      if (this.onZoom) this.onZoom();
    }
    resize() {
      const source = this.active || this.panes[0];
      const positions = this.panes.map(pane => ({
        y: fraction(pane.scrollTop, pane.scrollHeight - pane.clientHeight),
        x: fraction(pane.scrollLeft, pane.scrollWidth - pane.clientWidth)
      }));
      const shared = positions[this.panes.indexOf(source)];
      this.papers.forEach((paper, i) => {
        paper.style.width = `${Math.max(80, this.panes[i].clientWidth - 24) * this.scales[i] / 100}px`;
      });
      this.panes.forEach((pane, i) => {
        const position = this.enabled ? shared : positions[i];
        const top = position.y * Math.max(0, pane.scrollHeight - pane.clientHeight);
        const left = position.x * Math.max(0, pane.scrollWidth - pane.clientWidth);
        this.expected.set(pane, {top, left});
        pane.scrollTop = top;
        pane.scrollLeft = left;
      });
    }
    reset() {
      this.active = this.panes[0];
      this.panes.forEach(pane => {
        this.expected.set(pane, {top: 0, left: 0});
        pane.scrollTop = 0;
        pane.scrollLeft = 0;
      });
    }
  }
  root.PaperReader = {SynchronizedReader, fraction, documentTerms};
  if (typeof module !== 'undefined') module.exports = {SynchronizedReader, fraction, documentTerms};
})(typeof window === 'undefined' ? globalThis : window);
