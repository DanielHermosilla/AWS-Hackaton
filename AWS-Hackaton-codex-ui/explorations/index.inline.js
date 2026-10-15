const chosen=new Set();
    document.querySelectorAll('[data-concept]').forEach(button=>button.addEventListener('click',()=>{
      const name=button.dataset.concept;
      if(chosen.has(name))chosen.delete(name);else chosen.add(name);
      button.setAttribute('aria-pressed',String(chosen.has(name)));button.textContent=chosen.has(name)?'★':'☆';
      document.querySelector('#shortlist-status').textContent=chosen.size?'Para conversar: '+[...chosen].join(' · '):'Ninguna propuesta destacada';
    }));
