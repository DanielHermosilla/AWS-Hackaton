# web-login — ZMD Mobility

Web del **login** aislada de su proyecto de origen (AWS-Hackaton), con las vistas
de interfaz necesarias para navegarla. Es un **prototipo de interfaz**: la
validación de formulario funciona del lado del cliente, pero **no hay backend de
autenticación real**. La autenticación se conecta aparte (ver abajo).

## Contenido

```
web-login/
├─ index.html              Índice aislado (acceso + 4 vistas)
├─ gallery.css             Estilo del índice
├─ shared/                 Sistema de diseño compartido
│  ├─ tokens.css           Paleta y tokens (--ink, --surface, --line, ...)
│  ├─ demo.css             Base (Inter, botones .btn, .eyebrow, diálogos)
│  └─ demo.js              Lógica compartida de las vistas de demo
└─ interfaces/
   ├─ acceso/              EL LOGIN  (index.html, style.css, app.js)
   ├─ atlas/               Vista: mapa como espacio de trabajo
   ├─ balance/             Vista: comparación de dos vehículos
   ├─ cuaderno/            Vista: plan como documento
   └─ secuencia/           Vista: flujo guiado por etapas
```

## Ejecutar localmente

Requiere solo un servidor estático (no hay build):

```powershell
python -m http.server 4173 --bind 127.0.0.1 --directory .
# luego abrir:
#   http://127.0.0.1:4173/                     índice
#   http://127.0.0.1:4173/interfaces/acceso/    el login
```

Para exponerlo a la red local, usar `--bind 0.0.0.0` y abrir el puerto en el
firewall (perfil privado).

## Integración de la autenticación real

Todo el acceso real está aislado en una sola función de `interfaces/acceso/app.js`:

```js
async function enviarCredenciales({ email, password, remember }) { ... }
```

Hoy está simulada. Para conectarla con la otra web, reemplazar su cuerpo por una
llamada real (p. ej. `fetch` POST al endpoint de login) que devuelva
`{ ok, token }` o `{ ok:false, error }`. La UI y la validación ya están listas.

## Estética

Replica la propuesta **Balance** de ZMD Mobility: tipografía Inter + titulares
serif Georgia, paleta crema (`--surface`), bordes finos de 1px y el botón
primario oscuro (`--ink`). No introduce estilos nuevos: reutiliza `tokens.css` y
`demo.css`.
