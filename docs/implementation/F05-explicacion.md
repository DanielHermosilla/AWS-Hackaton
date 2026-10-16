# F05 · corregir una ubicación

**Qué hace.** Corrige un depósito, destino o cargador del CSV: dirección escrita,
coordenadas o marcador en el mapa.

**Cómo se agregó.** Editas una copia: Cancelar conserva el original; Confirmar
guarda los cambios y exige recalcular. El formulario funciona sin mapa.

**Límites.** Los CSV usan distancias aproximadas, sin comprobar calles. Un JSON
con red preparada conserva sus puntos protegidos: moverlos exige rehacer los
tramos. La búsqueda es local; una dirección escrita no obtiene coordenadas.

**Para Daniel — implementación.** Borrador persistido en la pestaña, coordenadas
validadas y resultados invalidados al confirmar. Reutiliza `/prepare` y `/solve`.
Quedan la reconstrucción vial y el [autocomplete externo](F05-address-autocomplete.md),
sujeto a acceso y cobertura.
