# Ronda 3 — refinar el mapa elegido

Fuente: instrucción de Diego del 15-10-2026, America/Santiago.

Diego eligió **Mapa de flota**, opción 1 de la ronda 2, como base. Pidió conservarla exactamente y preparar tres variantes cercanas: cuatro en total. Las opciones 2, 3 y 4 anteriores quedan descartadas de esta comparación; sus originales permanecen como historial. Las preguntas sobre variables se posponen hasta recibir las respuestas del equipo.

| Variante | Tratamiento |
|---|---|
| 01 · Original | La página original de `../round-2/mapa/`, sin modificar sus archivos ni dependencias. |
| 02 · Batería integrada | Perfil pequeño dentro de cada vehículo, ampliable y relacionado con sus paradas. |
| 03 · Cristal | Material translúcido en controles; tarjetas y cifras sobre superficies opacas. |
| 04 · Esencial | Menor altura de tarjetas, jerarquía tipográfica sobria y detalle reversible con Motion. |

La galería permite abrir cada página o alternar las cuatro dentro de un comparador. La selección final sigue correspondiendo a Diego. Estas páginas no eligen un reemplazo de Streamlit ni implementan el motor.

## Ejecutar y conservar la base

Servidor desde el worktree:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory explorations
```

Abrir `/round-3/`. El servidor existente ya sirve esta carpeta.

`qa/baseline-sha256.json` registra 18 archivos del mapa original y sus dependencias, incluidos los archivos locales. Se comparan al cerrar la ronda. Ninguna corrección de los nuevos diseños se aplica retroactivamente a la original.

Los módulos de presentación nuevos están en `shared/`; la distribución MapLibre, su licencia y el estilo de mapa se reutilizan desde la ronda 2 sin modificarlos. Los JSON locales se copiaron sin recalcular rutas ni energía. No se hicieron nuevas consultas de rutas a OSRM.

En otra máquina, preparar primero el ejemplo como indica el README de ronda 2 y copiar sus `shared/*.local.json` a `round-3/shared/`. Alternativamente, el script `round-3/shared/prepare-local-fixture.py` acepta el mismo CSV público y reutiliza las respuestas OSRM guardadas; consulta OSRM si faltan. Es exclusivamente un preparador de la demostración, no un cargador de escenarios del producto.

## Datos y alcance

Se mantienen los 81 nodos públicos, dos vehículos, asignaciones manuales, geometrías y cifras de la ronda 2. Los 16 kWh de capacidad solo mantienen la aritmética del ejemplo: no son una decisión sobre la capacidad útil del desafío.

Los perfiles muestran batería al llegar y salir de las paradas ya existentes. La recarga produce un incremento explícito. El depósito puede aparecer dos veces; la identidad de una parada seleccionada incluye vehículo e índice, no solo `BASE`.

No se añadieron ahorro, disponibilidad, tiempo de cómputo, autonomía estimada, nuevas variables del motor ni telemetría. La demostración no acredita factibilidad energética.

## Materiales y movimiento

Skills aplicadas selectivamente: `zmd-apple-design`, su referencia de interacción, `apple-design`, `animate` y `zmd-ui-qa`.

Apple distingue la capa de controles/navegación del contenido. Cristal adapta ese criterio a la web: el tratamiento de vidrio no convierte todas las cifras en paneles transparentes. Incluye alternativas opacas para preferencias de accesibilidad.

Esencial utiliza **Motion 14.2.0**, la distribución JavaScript del proyecto que incluye Framer Motion, vendorizada sin modificar y con licencia MIT. No se agregó React solo para animar. La transición tiene un propósito acotado: conservar orientación al abrir y cerrar el detalle de una parada. Usa `animateMini` para DOM, transform/opacity, spring sin rebote, duración de 200 ms, cancelación de cierres anteriores y captura del valor visual actual al invertir la acción. La API DOM evita que una escritura tardía de MotionValue restaure una opacidad intermedia después de una acción de teclado. Los cambios entre paradas abiertas son inmediatos. Teclado y movimiento reducido omiten la transición.

No hay animación de conteos, batería o energía. Las microinteracciones simples de las otras variantes usan CSS.

Fuentes primarias consultadas por HTTPS el 15-10-2026:

- Apple Human Interface Guidelines, Materials: `https://developer.apple.com/design/human-interface-guidelines/materials` y contenido oficial `https://developer.apple.com/tutorials/data/design/human-interface-guidelines/materials.json`.
- Repositorio oficial Motion: `https://github.com/motiondivision/motion`, README de `packages/motion`.
- Distribución y metadatos publicados por Motion: `https://registry.npmjs.org/motion/14.2.0`.

Las páginas `motion.dev/docs/animate` y `motion.dev/docs/react-accessibility` devolvieron HTTP 403 a la lectura automatizada; la implementación se contrastó con la distribución oficial y se ejecutó en Chrome.

## Autoría y trabajo paralelo

Astra coordina la ronda, el comparador y Esencial; los agentes de Codex implementan Batería integrada y Cristal. Se solicitó una crítica breve de Opus 5.5/max mediante Kiro en una sesión propia; su resultado y límites se registran en `docs/UI-RONDA-3.md`. No se atribuye código a Opus si solo entrega revisión textual.

Diego pidió un chat separado llamado **logo**, creado con Astra 6: `01a13dc0-6ef2-7893-aa59-cc691b35901d`. Trabaja en 40 ideas e HTML interactivo, con ámbito exclusivo `explorations/logo-40/` y `docs/LOGO-40-HANDOFF.md`. Su trabajo no condiciona la revisión de esta ronda de interfaz.

## Verificación

Las pruebas se acotan a presentación e interacción: computador, móvil secundario, selección sincronizada, depósito repetido, foco, preferencias de movimiento y conservación de la base. Resultados y capturas en `qa/`; cierre independiente **PASS acotado** en `qa/independent-review.md`. Se corrigieron contraste del perfil, dos interrupciones de Motion y el manejo de Escape dentro del comparador. No equivalen a pruebas del motor ni a una certificación global de accesibilidad. Batería documenta como límite secundario la posible cobertura del marcador por su detalle en móvil; la cámara se puede afinar tras elegir variante.
