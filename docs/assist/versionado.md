# Versionado por tags y reversión rápida pre-competencia

> Instruido por **Ateuluz** — seguridad operativa y plan de reversión.

Objetivo: si la integración de `assist` (u otra) deja `main` inestable cerca de
la competencia, poder volver a un punto bueno conocido en segundos, sin perder
historial y sin operaciones destructivas.

## Principio

Cada vez que `main` quede en un estado estable y demostrable, **crear un tag
anotado**. Un tag es un marcador inmutable: no se mueve con nuevos commits, así
que siempre podrás volver exactamente a él.

## Convención de tags

Semver con prefijo `v` y, para hitos de competencia, un sufijo claro:

- `v0.1.0-pre-assist` — estado estable ANTES de integrar el asistente.
- `v0.2.0-assist` — estado estable CON el asistente integrado y verificado.
- `v1.0.0-demo` — build congelado para la demo de la competencia.

Tag anotado (lleva autor, fecha y mensaje; preferirlo sobre tags ligeros):

```bash
git tag -a v0.1.0-pre-assist -m "Estado estable antes de integrar assist (Ateuluz)"
git push origin v0.1.0-pre-assist   # solo con aprobación
```

## Crear el tag de respaldo ANTES de integrar

Antes de fusionar `feat/ia-asistente-explicacion` a `main`, taggear el `main`
actual como red de seguridad:

```bash
git fetch origin
git tag -a v0.1.0-pre-assist origin/main -m "Respaldo pre-assist (Ateuluz)"
# push del tag solo tras aprobación explícita
```

## Reversión rápida (3 escenarios)

### A. Aún no se hizo push del merge
```bash
git switch main
git reset --soft HEAD~1    # deshace el merge local, conserva cambios en el índice
```
`--soft` NO borra trabajo. Evitar `--reset --hard` salvo decisión explícita.

### B. Ya se hizo push y hay que volver sin reescribir historia (recomendado)
```bash
git switch main
git revert -m 1 <sha-del-merge>   # crea un commit que deshace el merge
git push origin main              # solo con aprobación
```
`revert` es NO destructivo: deja el historial intacto y es seguro en ramas
compartidas. Es el método preferido en competencia.

### C. Desplegar directamente desde el último tag bueno
Si el servidor de la demo saca el código de un checkout, apuntar al tag:
```bash
git fetch --tags
git checkout v0.1.0-pre-assist   # estado detached: solo para servir la demo
```

## Qué NO hacer en ramas compartidas

> Instruido por **Ateuluz**.

- No `git push --force` ni `--force-with-lease` sobre `main`.
- No `git reset --hard` sobre ramas que otros usan.
- No borrar tags publicados (`git push --delete`) sin acordarlo con el equipo.

Preferir siempre `git revert` + tags: deja evidencia y es reversible.

## Checklist antes de la competencia

- [ ] Tag `vX-pre-assist` creado sobre el `main` estable previo.
- [ ] `assist` integrado y E2E verde (ver `docs/assist/e2e.md`).
- [ ] Tag `vX-assist` creado sobre el `main` ya integrado y verificado.
- [ ] Documentado el `sha` del merge para un `revert` inmediato.
- [ ] Confirmado que el servidor de demo puede apuntar a un tag.
