// Stack camera, vehicle and audio controls; keep logs below all cards.
(() => {
  const grid = document.querySelector('.grid');
  if (!grid) return;
  const vehicle = grid.querySelector('[data-module="vehicle"]');
  const camera = grid.querySelector('[data-module="camera"]');
  const audio = grid.querySelector('[data-module="audio"]');
  const logs = grid.querySelector('[data-module="logs"]');
  if (vehicle && camera) camera.after(vehicle);
  if (vehicle && audio) vehicle.after(audio);
  if (logs) grid.append(logs);
  let pending = false;
  function layout() {
    pending = false;
    const width = grid.clientWidth;
    if (!width) return;
    const gap = 20;
    const columns = Math.max(1, Math.min(3, Math.floor((width + gap) / 380)));
    const cardWidth = (width - gap * (columns - 1)) / columns;
    const heights = Array(columns).fill(0);
    let cameraColumn = null;
    let vehicleColumn = null;
    grid.classList.add('flow-layout');
    for (const card of grid.children) {
      if (card.hidden || getComputedStyle(card).display === 'none') continue;
      const full = ['waveform', 'logs'].includes(card.dataset.module);
      const anchor = card === vehicle ? cameraColumn : card === audio ? (vehicleColumn ?? cameraColumn) : null;
      const column = full ? 0 : anchor !== null ? anchor : heights.indexOf(Math.min(...heights));
      const top = full ? Math.max(...heights) : heights[column];
      card.style.width = `${full ? width : cardWidth}px`;
      card.style.left = `${column * (cardWidth + gap)}px`;
      card.style.top = `${top}px`;
      const bottom = top + card.getBoundingClientRect().height + gap;
      if (full) heights.fill(bottom);
      else heights[column] = bottom;
      if (card === camera) cameraColumn = column;
      if (card === vehicle) vehicleColumn = column;
    }
    grid.style.height = `${Math.max(0, ...heights) - (heights.some(Boolean) ? gap : 0)}px`;
  }
  function schedule() {
    if (!pending) { pending = true; requestAnimationFrame(layout); }
  }
  const resize = new ResizeObserver(schedule);
  resize.observe(grid);
  for (const card of grid.children) resize.observe(card);
  new MutationObserver(schedule).observe(grid, {
    subtree: true, attributes: true, attributeFilter: ['hidden'], childList: true,
  });
  window.addEventListener('resize', schedule);
  document.fonts?.ready.then(schedule);
  schedule();
})();
