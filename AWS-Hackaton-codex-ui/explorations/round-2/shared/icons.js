const paths = {
  arrow:'<path d="m9 5 7 7-7 7"/>',
  back:'<path d="m14 5-7 7 7 7"/>',
  map:'<path d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5Zm6-2v16m6-14v16"/>',
  car:'<path d="m4 10 2-5h12l2 5M3 10h18v8H3zM5 18v3m14-3v3M6 14h2m8 0h2"/>',
  battery:'<rect x="2" y="6" width="18" height="12" rx="3"/><path d="M23 10v4M6 10v4m4-4v4m4-4v4"/>',
  bolt:'<path d="m13 2-9 12h7l-1 8 10-12h-8l1-8Z"/>',
  plug:'<path d="M8 2v5m8-5v5M6 7h12v3a6 6 0 0 1-12 0V7Zm6 9v6"/>',
  box:'<path d="m12 3 9 5v9l-9 5-9-5V8l9-5ZM3 8l9 5 9-5m-9 5v9M7.5 5.5l9 5"/>',
  base:'<path d="m3 10 9-7 9 7v11H3V10Zm5 11v-8h8v8"/>',
  target:'<circle cx="12" cy="12" r="7"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/>',
  layers:'<path d="m12 3 10 6-10 6L2 9l10-6Zm-9 11 9 5 9-5m-18 5 9 5 9-5"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
  route:'<circle cx="5" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M7 5h9a4 4 0 0 1 0 8H8a4 4 0 0 0 0 8h9"/>',
  play:'<path d="m8 4 13 8-13 8V4Z"/>',
  pause:'<path d="M8 4v16M16 4v16"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  close:'<path d="m6 6 12 12M18 6 6 18"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>'
};
export function icon(name, size=20) { size = Number.isFinite(+size) ? +size : 20; return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.info}</svg>`; }
export function carDrawing(color = '#1664ec') {
  // El color llega de datos: solo se acepta #rrggbb (evita inyectar atributos SVG).
  if (!/^#[0-9a-fA-F]{6}$/.test(String(color))) color = '#1664ec';
  return `<svg viewBox="0 0 220 92" role="img" aria-label="Ilustración de vehículo eléctrico" class="car-drawing">
  <ellipse cx="111" cy="77" rx="93" ry="6" fill="#121926" opacity=".08"/>
  <path d="M20 55 32 40 55 32 79 14q5-4 14-4h39q15 0 25 13l14 19 27 9q8 3 9 10v11H14V60q0-4 6-5Z" fill="${color}"/>
  <path d="m62 33 23-17h45q13 0 21 11l8 11-97-5Z" fill="#d6eafa"/>
  <path d="M106 16v19m-52 7 118 5" stroke="#163a59" stroke-opacity=".28" stroke-width="2"/>
  <path d="M18 57h19m153-2 13 5" stroke="#fff" stroke-width="5" stroke-linecap="round"/>
  <path d="M78 41v22m60-20 7 22m-58-17h10m48 4h9" stroke="#091d38" stroke-opacity=".3" stroke-width="2"/>
  <circle cx="53" cy="70" r="16" fill="#172434"/><circle cx="53" cy="70" r="9" fill="#c5d0de"/><circle cx="53" cy="70" r="4" fill="#708090"/>
  <circle cx="169" cy="70" r="16" fill="#172434"/><circle cx="169" cy="70" r="9" fill="#c5d0de"/><circle cx="169" cy="70" r="4" fill="#708090"/>
  <path d="m114 44-7 9h6l-2 8 9-12h-6l1-5Z" fill="#fff"/>
  </svg>`;
}
