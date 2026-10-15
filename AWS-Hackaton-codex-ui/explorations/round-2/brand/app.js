(() => {
  const proposals = window.ZMD_ROUND_2;
  const gallery = document.querySelector('#gallery');
  const dialog = document.querySelector('#detail');
  const body = document.body;
  let active = null;
  let opener = null;

  function labelSvg(source) {
    const box = document.createElement('div');
    box.innerHTML = source;
    return box.firstElementChild;
  }

  for (const [index, proposal] of proposals.entries()) {
    const card = document.createElement('article');
    card.className = 'card';
    card.dataset.family = proposal.family;
    card.dataset.id = proposal.id;
    const stage = document.createElement('button');
    stage.type = 'button';
    stage.className = 'logo-stage';
    stage.setAttribute('aria-label', `Ver detalle de ${proposal.name}`);
    const logo = labelSvg(proposal.svg);
    logo.setAttribute('aria-hidden', 'true');
    stage.append(logo);
    const copy = document.createElement('div');
    copy.className = 'card-copy';
    copy.innerHTML = `<div class="card-heading"><span class="card-number">${String(index + 1).padStart(2, '0')}</span><h2></h2></div><p></p><div class="card-bottom"><span class="family-label"></span><button type="button" class="detail-link">Ver detalle <span aria-hidden="true">↗</span></button></div>`;
    copy.querySelector('h2').textContent = proposal.name;
    copy.querySelector('p').textContent = proposal.meaning;
    copy.querySelector('.family-label').textContent = proposal.family_label;
    const detailButton = copy.querySelector('.detail-link');
    detailButton.setAttribute('aria-label', `Ver detalle de ${proposal.name}`);
    stage.addEventListener('click', () => openDetail(proposal, index, stage));
    detailButton.addEventListener('click', () => openDetail(proposal, index, detailButton));
    card.append(stage, copy);
    gallery.append(card);
  }

  function openDetail(proposal, index, trigger) {
    active = proposal;
    opener = trigger;
    document.querySelector('#detail-family').textContent = proposal.family_label;
    document.querySelector('#detail-number').textContent = `PROPUESTA ${String(index + 1).padStart(2, '0')} / 12`;
    document.querySelector('#detail-title').textContent = proposal.name;
    document.querySelector('#detail-meaning').textContent = proposal.meaning;
    document.querySelector('#detail-risk').textContent = proposal.risk;
    document.querySelector('#detail-logo').replaceChildren(labelSvg(proposal.svg));
    const symbols = [20, 32, 64].map(size => {
      const svg = labelSvg(proposal.symbol_svg);
      svg.setAttribute('width', size);
      svg.setAttribute('height', size);
      return svg;
    });
    document.querySelector('#detail-symbols').replaceChildren(...symbols);
    document.querySelector('#download-symbol').href = proposal.symbol;
    dialog.showModal();
    document.querySelector('#close-detail').focus();
  }

  document.querySelector('#close-detail').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => opener?.focus());
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const {left, right, top, bottom} = dialog.getBoundingClientRect();
    if (event.clientX < left || event.clientX > right || event.clientY < top || event.clientY > bottom) dialog.close();
  });

  for (const button of document.querySelectorAll('[data-filter]')) {
    button.addEventListener('click', () => {
      const family = button.dataset.filter;
      for (const sibling of document.querySelectorAll('[data-filter]')) sibling.setAttribute('aria-pressed', String(sibling === button));
      let count = 0;
      for (const card of gallery.children) {
        card.hidden = family !== 'all' && card.dataset.family !== family;
        if (!card.hidden) count++;
      }
      document.querySelector('#count').textContent = `${count} propuestas`;
    });
  }

  for (const [attribute, dataName] of [['data-theme-choice', 'theme'], ['data-palette-choice', 'palette']]) {
    const buttons = document.querySelectorAll(`[${attribute}]`);
    for (const button of buttons) {
      button.addEventListener('click', () => {
        body.dataset[dataName] = button.getAttribute(attribute);
        for (const sibling of buttons) sibling.setAttribute('aria-pressed', String(sibling === button));
      });
    }
  }

  document.querySelector('#download-current').addEventListener('click', () => {
    if (!active) return;
    const style = getComputedStyle(body);
    const ink = style.getPropertyValue('--logo-ink').trim();
    const accent = body.dataset.palette === 'black' ? ink : style.getPropertyValue('--logo-accent').trim();
    const source = active.svg
      .replace(/var\(--logo-ink, #[0-9a-fA-F]+\)/g, ink)
      .replace(/var\(--logo-accent, #[0-9a-fA-F]+\)/g, accent);
    const url = URL.createObjectURL(new Blob([source], {type: 'image/svg+xml'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = `${active.id}-${body.dataset.theme}-${body.dataset.palette}.svg`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
})();
