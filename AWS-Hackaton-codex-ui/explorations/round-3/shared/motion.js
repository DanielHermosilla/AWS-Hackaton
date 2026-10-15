import './vendor/motion-14.2.0.js';

// Motion's browser distribution includes the same animation engine as Framer Motion.
// The DOM-only API commits native styles synchronously on stop. The hybrid API
// can queue a MotionValue render after a keyboard action has settled the panel.
const { animateMini: animate, spring } = globalThis.Motion;
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
let keyboard = false;
document.addEventListener('keydown', () => { keyboard = true; }, true);
document.addEventListener('pointerdown', () => { keyboard = false; }, true);

/**
 * A reversible, nonmodal detail surface. Changing the selected stop while open
 * updates its text immediately; only entering/leaving the surface has motion.
 */
export function detailSurface(element) {
  let controls;
  let generation = 0;
  let wanted = false;
  const settle = (open) => {
    element.hidden = !open;
    element.style.opacity = open ? '1' : '0';
    element.style.transform = open ? 'translateY(0px)' : 'translateY(8px)';
  };
  function set(open) {
    const token = ++generation;
    const wasHidden = element.hidden;
    const wasAnimating = !!controls;
    wanted = open;
    if (controls) {
      const visual = getComputedStyle(element);
      const opacity = visual.opacity, transform = visual.transform;
      controls.stop();
      element.style.opacity = opacity;
      element.style.transform = transform;
      controls = undefined;
    }
    element.inert = !open;
    if (reduced.matches || keyboard || (open && !wasHidden && !wasAnimating)) {
      settle(open);
      return;
    }
    if (open && wasHidden) {
      element.hidden = false;
      element.style.opacity = '0';
      element.style.transform = 'translateY(8px)';
    }
    if (!open && wasHidden) return;
    controls = animate(element, {
      opacity: open ? 1 : 0,
      transform: open ? 'translateY(0px)' : 'translateY(8px)'
    }, { type: spring, duration: .2, bounce: 0 });
    controls.then(() => {
      if (token !== generation) return;
      controls = undefined;
      settle(open);
    });
  }
  reduced.addEventListener('change', () => {
    if (!reduced.matches) return;
    ++generation;
    // Settle at the intended endpoint when the preference changes mid-flight.
    controls?.complete();
    controls = undefined;
    settle(wanted);
  });
  return { show: () => set(true), hide: () => set(false) };
}
