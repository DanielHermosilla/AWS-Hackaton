const themeButtons = document.querySelectorAll('[data-theme]');
const sizeButtons = document.querySelectorAll('[data-size]');
const selectButtons = document.querySelectorAll('[data-select]');
const status = document.getElementById('selection-status');
for (const button of themeButtons) button.addEventListener('click', () => {
 const dark = button.dataset.theme === 'dark';
 document.body.classList.toggle('dark', dark);
 for (const control of themeButtons) control.setAttribute('aria-pressed', String(control === button));
});
for (const button of sizeButtons) button.addEventListener('click', () => {
 document.documentElement.style.setProperty('--symbol-size', `${button.dataset.size}px`);
 for (const control of sizeButtons) control.setAttribute('aria-pressed', String(control === button));
 for (const label of document.querySelectorAll('.size-readout')) label.textContent = `${button.dataset.size} px`;
});
for (const button of selectButtons) button.addEventListener('click', () => {
 const wasSelected = button.getAttribute('aria-pressed') === 'true';
 for (const control of selectButtons) {
  const selected = control === button && !wasSelected;
  control.setAttribute('aria-pressed', String(selected));
  control.closest('.concept').classList.toggle('is-selected', selected);
  control.firstChild.textContent = selected ? 'Destacado ' : 'Destacar ';
 }
 status.replaceChildren();
 if (wasSelected) { status.textContent = 'Ninguna dirección destacada'; return; }
 const strong = document.createElement('strong');
 strong.textContent = button.closest('.concept').querySelector('h2').textContent;
 status.append('En foco: ', strong);
});
