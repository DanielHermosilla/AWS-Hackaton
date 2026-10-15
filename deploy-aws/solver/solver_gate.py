"""Gate de acceso por token secreto para el solver Streamlit.

El solver no debe tener enlace público visible: solo entra quien conozca la URL
con el token correcto, p. ej.:

    https://<host>/?token=EL_TOKEN_SECRETO

El token se define en la variable de entorno SOLVER_TOKEN. Si no está definida,
el gate queda ABIERTO (útil solo en desarrollo local).

Uso en app.py:

    from solver_gate import exigir_token
    exigir_token()   # al inicio; detiene la app si el token no coincide
"""
from __future__ import annotations

import os

import streamlit as st

_SESSION_FLAG = "_solver_autorizado"


def exigir_token() -> None:
    token_esperado = os.getenv("SOLVER_TOKEN", "").strip()

    # Sin token configurado => acceso abierto (desarrollo local).
    if not token_esperado:
        return

    # Ya autorizado en esta sesión del navegador.
    if st.session_state.get(_SESSION_FLAG):
        return

    # Leer el token de los query params (?token=...).
    try:
        params = st.query_params
        token_recibido = params.get("token", "")
    except Exception:
        # Compatibilidad con versiones antiguas de Streamlit.
        token_recibido = st.experimental_get_query_params().get("token", [""])[0]

    if token_recibido and token_recibido == token_esperado:
        st.session_state[_SESSION_FLAG] = True
        return

    # Acceso denegado: no revelar nada del contenido.
    st.set_page_config(page_title="No disponible", page_icon="🔒")
    st.title("🔒 Acceso restringido")
    st.write("Esta página requiere una URL de acceso válida.")
    st.stop()
