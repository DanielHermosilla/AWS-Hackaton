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

### v2 — Login + registro integrados en la webapp, con backend real (recomendado)
Versión final: login y **registro** viven **dentro de la webapp real** de
planificación, con un **backend de verdad** (FastAPI + SQLite + bcrypt) que sirve
la web y gestiona cuentas y sesiones. Estética definitiva: Inter, azul `#1664ec`,
logo "Batería en marcha".

Seguridad real incluida: contraseñas con **bcrypt**, sesión por **cookie
httpOnly** con token aleatorio y expiración, validación en servidor, **rate
limiting** por IP y **protección de rutas** (`index.html`/`plan.html` exigen
sesión). Detalles en `v2/server/README.md`.

Flujo: `login.html` ⇄ `register.html` → `index.html` (Inicio) → `plan.html` …
"Salir" cierra la sesión en el servidor → `salida.html` → vuelve a `login.html`.

- Correr (¡con el backend, no http.server!):
  ```
  cd v2/server
  python -m pip install -r requirements.txt
  python -m uvicorn app:app --host 127.0.0.1 --port 4173
  ```
  Abrir `http://127.0.0.1:4173/login.html`.
  En red local: `--host 0.0.0.0` + abrir el puerto 4173 en el firewall.

## Acceso

- **v1**: demo de interfaz; cualquier correo válido + contraseña 8+ "entra".
- **v2**: cuentas **reales** gestionadas por el backend. Regístrate en
  `register.html` (contraseña fuerte: 10+ con mayús, minús, número y símbolo) y
  luego inicia sesión. La sesión se guarda en una cookie segura del servidor.

## Integración / backend real

- **v1** (solo frontend): el punto de integración está en
  `v1/interfaces/acceso/app.js` → `enviarCredenciales(...)`.
- **v2** (ya tiene backend): el backend FastAPI está en `v2/server/`. El cliente
  (`v2/auth.js`) usa `API.base=''` (mismo origen). Para mover la auth a otro
  host, cambiar `API.base` y habilitar CORS + cookies cross-site. Para producción
  con HTTPS, poner `secure=True` en la cookie (`v2/server/app.py`).
