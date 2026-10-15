(() => {
  const key = 'zmd.homepage.console-theme.v1';
  const root = document.documentElement;
  let theme = 'dark';
  try {
    if (localStorage.getItem(key) === 'light') theme = 'light';
  } catch { /* The selector also works without storage. */ }

  // Apply before the page paints, including a previously chosen light theme.
  root.dataset.consoleTheme = theme;

  document.addEventListener('DOMContentLoaded', () => {
    const inputs = document.querySelectorAll('input[name="console-theme"]');
    for (const input of inputs) {
      input.checked = input.value === theme;
      input.addEventListener('change', () => {
        if (!input.checked) return;
        theme = input.value;
        root.dataset.consoleTheme = theme;
        try { localStorage.setItem(key, theme); } catch { /* Keep this view usable. */ }
      });
    }
  });
})();
