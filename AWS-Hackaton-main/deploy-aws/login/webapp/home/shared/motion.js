import '../../vendor/motion/motion-14.2.0.js';

const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const controls = new Map();
function finishAll() {
  for (const control of controls.values()) control.complete();
  controls.clear();
}
reduced.addEventListener('change', finishAll);
for (const disclosure of document.querySelectorAll('.data-note')) {
  const detail = disclosure.querySelector('[data-motion-detail]');
  if (!detail) continue;
  disclosure.addEventListener('toggle', () => {
    controls.get(detail)?.complete();
    controls.delete(detail);
    if (!disclosure.open || reduced.matches) return;
    const control = globalThis.Motion.animateMini(detail, { opacity: [0, 1], transform: ['translateY(-3px)', 'translateY(0)'] }, { duration: .15, ease: [.22, 1, .36, 1] });
    controls.set(detail, control);
    control.then(() => { if (controls.get(detail) === control) controls.delete(detail); });
  });
}
