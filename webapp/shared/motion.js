import '../vendor/motion/motion-14.2.0.js';
import { prefersReducedMotion, onReducedMotionChange } from '../state.js';

// Motion's browser distribution includes the same animation engine as Framer Motion.
// The DOM-only API commits native styles synchronously on stop. The hybrid API
// can queue a MotionValue render after a keyboard action has settled the panel.
const { animateMini: animate, spring } = globalThis.Motion;
let keyboard = false;
document.addEventListener('keydown', () => { keyboard = true; }, true);
document.addEventListener('pointerdown', () => { keyboard = false; }, true);

/**
 * A reversible, nonmodal detail surface. Changing the selected stop while open
 * updates its text immediately; only entering/leaving the surface has motion.
 * Keyboard use and reduced motion (system or local preference) settle at once.
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
      // Interrupt from the current visual state instead of jumping to an endpoint.
      const visual = getComputedStyle(element);
      const opacity = visual.opacity, transform = visual.transform;
      controls.stop();
      element.style.opacity = opacity;
      element.style.transform = transform;
      controls = undefined;
    }
    element.inert = !open;
    if (prefersReducedMotion() || keyboard || (open && !wasHidden && !wasAnimating)) {
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
  onReducedMotionChange(reduced => {
    if (!reduced) return;
    ++generation;
    // Settle at the intended endpoint when the preference changes mid-flight.
    controls?.complete();
    controls = undefined;
    settle(wanted);
  });
  return { show: () => set(true), hide: () => set(false) };
}
