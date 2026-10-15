"""Entrypoint del solver Streamlit para el contenedor AWS.

Aplica el gate de token secreto y luego ejecuta la app real del solver (app.py).
Streamlit ejecuta este archivo; al importar app.py se renderiza la interfaz
completa, pero solo si el token fue válido.
"""
from solver_gate import exigir_token

exigir_token()  # detiene aquí si la URL no trae el token correcto

# Importa y ejecuta la app real del solver (todo su código corre al importar).
import app  # noqa: E402,F401
