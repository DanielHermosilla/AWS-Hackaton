const options=window.ZMD_IDENTITY_OPTIONS||[];
const families={electric:'Electromovilidad',efficiency:'Eficiencia',value:'Ahorro',intelligence:'IA'};
const chosen=new Set();let filter='all';
const grid=document.querySelector('#concepts'),detail=document.querySelector('#detail');
function render(){
 const visible=options.filter(c=>filter==='all'||filter==='recommended'&&c.recommended||c.family===filter);
 grid.innerHTML=visible.map(c=>`<article class="concept ${chosen.has(c.id)?'chosen':''}" id="${c.id}"><div class="concept-top"><span>${String(options.indexOf(c)+1).padStart(2,'0')} / ${families[c.family]}</span>${c.recommended?'<span class="recommended">Preselección</span>':''}</div><button class="symbol" data-open="${c.id}" aria-label="Ver concepto ${c.name}"><img src="${c.symbol}" alt=""></button><div class="concept-copy"><h3>${c.name}</h3><p>${c.meaning}</p></div><div class="concept-actions"><button data-open="${c.id}">Ver firma ↗</button><button data-select="${c.id}" aria-label="Destacar ${c.name}" aria-pressed="${chosen.has(c.id)}">${chosen.has(c.id)?'★':'☆'}</button></div></article>`).join('');
 grid.querySelectorAll('[data-open]').forEach(b=>b.addEventListener('click',()=>openDetail(b.dataset.open)));
 grid.querySelectorAll('[data-select]').forEach(b=>b.addEventListener('click',()=>{if(chosen.has(b.dataset.select))chosen.delete(b.dataset.select);else chosen.add(b.dataset.select);const id=b.dataset.select;render();grid.querySelector(`[data-select="${id}"]`)?.focus({preventScroll:true});}));
 document.querySelector('#count').textContent=`${visible.length} conceptos${filter==='all'?' nuevos':' · '+(filter==='recommended'?'preselección para conversar':families[filter])}`;
 const bar=document.querySelector('#selection-bar');bar.hidden=!chosen.size;
 document.querySelector('#selection-label').textContent='Para refinar: '+options.filter(c=>chosen.has(c.id)).map(c=>c.name).join(' · ');
}
function openDetail(id){
 const c=options.find(c=>c.id===id);if(!c)return;
 document.querySelector('#detail-family').textContent=families[c.family];
 document.querySelector('#detail-title').textContent=c.name;
 document.querySelector('#detail-meaning').textContent=c.meaning;
 document.querySelector('#detail-symbol').src=c.symbol;
 document.querySelector('#detail-symbol').alt='Símbolo '+c.name;
 document.querySelector('#detail-light').src=c.light;
 document.querySelector('#detail-dark').src=c.dark;
 document.querySelector('#detail-risk').textContent='Para refinar: '+c.risk;
 document.querySelector('#download-symbol').href=c.symbol;
 document.querySelector('#download-light').href=c.light;
 document.querySelector('#download-dark').href=c.dark;
 detail.showModal();
}
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));render();}));
document.querySelector('#theme').addEventListener('click',e=>{const dark=document.body.classList.toggle('dark');const b=e.currentTarget;b.setAttribute('aria-pressed',String(dark));b.setAttribute('aria-label',dark?'Ver sobre fondo claro':'Ver sobre fondo oscuro');b.querySelector('span').textContent=dark?'Fondo claro':'Fondo oscuro';});
document.querySelector('#size').addEventListener('change',e=>document.documentElement.style.setProperty('--symbol-size',e.target.value+'px'));
document.querySelector('#clear').addEventListener('click',()=>{chosen.clear();render();document.querySelector('[data-filter="all"]').focus();});
document.querySelector('#close').addEventListener('click',()=>detail.close());
render();
