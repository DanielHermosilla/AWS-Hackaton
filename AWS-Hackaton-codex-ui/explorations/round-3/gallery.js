const paths = ['../round-2/mapa/', 'bateria/', 'cristal/', 'esencial/'];
const names = ['Original', 'Batería integrada', 'Cristal', 'Esencial'];
const dialog = document.querySelector('#comparison');
const frame = document.querySelector('#live-preview');
let current = -1;
function choose(index) {
  if (current === index) return;
  current = index;
  frame.src = paths[index];
  frame.title = `${index + 1}. ${names[index]} — mapa de flota interactivo`;
  document.querySelector('#open-full').href = paths[index];
  document.querySelectorAll('[data-variant]').forEach(el => {
    el.setAttribute('aria-pressed', String(Number(el.dataset.variant) === index));
  });
}
document.querySelectorAll('[data-preview]').forEach(el => {
  el.addEventListener('click', () => {
    choose(Number(el.dataset.preview));
    dialog.showModal();
    document.querySelector(`[data-variant="${current}"]`).focus();
  });
});
document.querySelectorAll('[data-variant]').forEach(el => {
  el.addEventListener('click', () => choose(Number(el.dataset.variant)));
});
document.querySelector('#close-comparison').onclick = () => dialog.close();
frame.addEventListener('load', () => {
  // Keyboard events stay inside an iframe. Handle the comparison boundary here,
  // without changing any of the four source pages (including the original).
  const embedded = frame.contentDocument;
  embedded?.querySelectorAll('a.all-designs, a.brand').forEach(link => {
    link.addEventListener('click', event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      dialog.close();
    });
  });
  embedded?.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || event.defaultPrevented) return;
    if (embedded.querySelector('dialog[open]')) return;
    const selection = embedded.querySelector('#selection');
    if (selection && !selection.hidden && !selection.inert) {
      embedded.querySelector('#close-selection')?.click();
    } else {
      dialog.close();
    }
    event.preventDefault();
    event.stopPropagation();
  }, true);
});
dialog.addEventListener('close', () => {
  // A closed comparison should not keep a WebGL map running offscreen.
  frame.removeAttribute('src');
  current = -1;
});
