# web-login — ZMD Mobility (versiones)

Branch de test con el **login** de ZMD Mobility, organizado por versiones para
verlo fácil. Es un prototipo de interfaz: la validación es del lado del cliente y
**no hay backend de autenticación real** (se conecta aparte).

## Versiones

```
web-login/
├─ v1/   Login inicial — estética "exploraciones" (propuesta Balance)
└─ v2/   Login integrado en la webapp real (recomendado)
```

### v1 — Login sobre las exploraciones de diseño
Primera versión. Replica la propuesta **Balance** de las exploraciones: tipografía
Inter + titulares serif Georgia, paleta crema, acento oscuro. Páginas sueltas
(login + 4 vistas de muestra), sin app alrededor.

- Entrada: `v1/index.html` (índice) o `v1/interfaces/acceso/` (el login).
- Correr: `python -m http.server 4173 --directory v1`

### v2 — Login integrado en la webapp (recomendado)
Versión final: el login vive **dentro de la webapp real** de planificación
(la de la branch `codex/webapp`). Adopta su estética definitiva: tipografía Inter,
azul `#1664ec`, logo de marca "Batería en marcha", reutilizando `shared/base.css`
y `app.css`. El acceso se enlaza con el flujo real de la app.

Flujo: `login.html` → `index.html` (Inicio) → `plan.html` (mapa) …
y "Salir de la demostración" → `salida.html` → vuelve a `login.html`.

- Entrada: `v2/login.html`
- Correr: `python -m http.server 4173 --directory v2`
  - En red local: añadir `--bind 0.0.0.0` y abrir el puerto 4173 en el firewall.

## Demostración de acceso

En ambas versiones, cualquier **correo válido** y una **contraseña de 8+
caracteres** entran. No se verifica nada contra un servidor.

## Integración de la autenticación real

El acceso real está aislado en una sola función:
- v1: `v1/interfaces/acceso/app.js` → `enviarCredenciales(...)`
- v2: `v2/login.js` → `enviarCredenciales(...)`

Reemplazar su cuerpo por una llamada real (p. ej. `fetch` POST al endpoint de
login) que devuelva `{ ok, token }` o `{ ok:false, error }`. La UI y la
validación ya están listas; solo cambia esa función.
