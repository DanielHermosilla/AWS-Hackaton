# Backend de autenticación — ZMD Mobility

Backend real que **sirve la webapp** y añade cuentas de usuario con sesión segura.
Stack: **FastAPI + SQLite + bcrypt**. Sin servicios externos.

## Correr

```powershell
# desde webapp/server/
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 4173
#   en red local:  --host 0.0.0.0   (y abrir el puerto 4173 en el firewall)
```

Luego abrir `http://127.0.0.1:4173/login.html`.
La webapp (index, plan, mapa) se sirve desde el mismo servidor.

> Importante: ahora la web se sirve con **uvicorn**, no con `python -m http.server`.
> El servidor estático no puede autenticar.

## Endpoints

| Método | Ruta             | Qué hace                                           |
|--------|------------------|----------------------------------------------------|
| POST   | `/auth/register` | Crea cuenta (hash bcrypt) e inicia sesión          |
| POST   | `/auth/login`    | Verifica credenciales e inicia sesión              |
| POST   | `/auth/logout`   | Invalida el token de sesión                        |
| GET    | `/auth/me`       | Devuelve el usuario de la sesión (401 si no hay)   |
| GET    | `/{ruta}`        | Sirve la webapp; protege `index.html` y `plan.html`|

## Seguridad aplicada

- **bcrypt** para contraseñas (sal única por hash; nunca se guarda la contraseña).
- Sesión por **token aleatorio** (`secrets.token_urlsafe`) con expiración (8 h);
  en la BD se guarda solo su **hash SHA-256**, no el token.
- Cookie **httpOnly + SameSite=Lax** (inaccesible a JS; mitiga XSS/CSRF básico).
  En producción con HTTPS, poner `secure=True` en `_set_cookie`.
- **Validación en el servidor** de email y política de contraseña (10+, mayús,
  minús, número, símbolo). No se confía en el cliente.
- **Rate limiting** por IP: login 10/10min, registro 5/10min.
- Comparación de contraseña en **tiempo ~constante** (verifica un hash aunque el
  usuario no exista) para no filtrar qué correos están registrados.
- Protección de **path traversal** al servir archivos estáticos.

## Base de datos

SQLite en `server/data/zmd.db` (creada al arrancar). **Ignorada por Git.**
Tablas: `users` (email único, nombre, password_hash) y `sessions`
(token_hash, user_id, expiración).

## Mover la auth a otro host

El frontend usa `API.base = ''` (mismo origen) en `auth.js`. Si la API vive en
otro dominio, cambiar `API.base` y habilitar CORS + cookies cross-site en el
servidor.
