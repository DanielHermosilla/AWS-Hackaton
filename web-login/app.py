"""App Streamlit para planificar rutas y recargas de vehículos eléctricos.

Conecta la librería `ev_routing` (carga de instancia, resolución del modelo MILP
con HiGHS y validación) con una interfaz local. Corre con:

    streamlit run app.py

No sube nada a AWS. Bedrock se usa solo si pulsas "Explicar con IA" y hay
credenciales activas (AWS_PROFILE).
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from typing import Optional

import pandas as pd
import streamlit as st

from ev_routing.contracts import FleetConfig, ProblemInstance, RunResult, SolverConfig
from ev_routing.inputs import load_problem_instance_from_csv
from ev_routing.pipeline import run


def _configurar_credenciales_aws() -> None:
    """Carga credenciales AWS para Bedrock.

    En Streamlit Cloud se leen desde st.secrets (panel 'Secrets', nunca en el repo).
    En local, si no hay secrets, se usa el perfil/entorno habitual (AWS_PROFILE).
    """
    try:
        secrets = st.secrets  # lanza si no hay archivo de secrets
    except Exception:
        return  # sin secrets: se usa el perfil local / variables de entorno
    if "AWS_ACCESS_KEY_ID" in secrets:
        os.environ["AWS_ACCESS_KEY_ID"] = secrets["AWS_ACCESS_KEY_ID"]
        os.environ["AWS_SECRET_ACCESS_KEY"] = secrets["AWS_SECRET_ACCESS_KEY"]
        if "AWS_SESSION_TOKEN" in secrets:
            os.environ["AWS_SESSION_TOKEN"] = secrets["AWS_SESSION_TOKEN"]
        os.environ["AWS_DEFAULT_REGION"] = secrets.get("AWS_DEFAULT_REGION", "us-east-1")

# Ruta al CSV de ejemplo del desafío.
# Prioriza la copia dentro del repo (para que funcione desplegado); si no está,
# usa la original en la carpeta Electromovilidad (desarrollo local).
_AQUI = os.path.dirname(__file__)
_CANDIDATOS_CSV = [
    os.path.join(_AQUI, "data_ejemplo", "competition_routing_nodes.csv"),
    os.path.join(_AQUI, "..", "Electromovilidad", "competition_routing_nodes.csv"),
]
EJEMPLO_CSV = next((p for p in _CANDIDATOS_CSV if os.path.exists(p)), _CANDIDATOS_CSV[0])

st.set_page_config(page_title="Ruteo EV", page_icon="🔋", layout="wide")

st.title("🔋 Planificación de rutas y recargas para vehículos eléctricos")
st.caption(
    "Carga nodos (depósito, locales y cargadores), resuelve el modelo y revisa "
    "entregas, batería y rutas. Todo en local."
)


# --------------------------------------------------------------------------- #
# Barra lateral: configuración de la instancia y el solver
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("Datos de entrada")
    fuente = st.radio(
        "Fuente de nodos",
        ["Ejemplo del desafío", "Subir CSV"],
        help="El CSV debe tener columnas: node_id, node_type, latitude, longitude, ...",
    )

    archivo_subido = None
    if fuente == "Subir CSV":
        archivo_subido = st.file_uploader("Archivo de nodos (.csv)", type=["csv"])

    st.header("Flota")
    num_vehiculos = st.number_input("N.º de vehículos", min_value=1, max_value=10, value=2)
    capacidad = st.number_input("Capacidad de batería (kWh)", min_value=1.0, value=24.0, step=1.0)
    soc_inicial = st.slider("Carga inicial (SOC)", 0.0, 1.0, 0.6, 0.05)
    reserva = st.number_input("Reserva mínima (kWh)", min_value=0.0, value=2.4, step=0.5)

    st.header("Modelo y solver")
    movimientos = st.number_input(
        "Límite de movimientos (H)", min_value=1, max_value=50, value=6,
        help="Cota del número de movimientos. Mayor H = más alcance pero más lento.",
    )
    tiempo_limite = st.number_input("Tiempo límite (s)", min_value=5, max_value=1800, value=120)

    resolver = st.button("▶ Resolver", type="primary", use_container_width=True)


def _ruta_csv_temporal(archivo) -> str:
    """Guarda un archivo subido en un .csv temporal y devuelve la ruta."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="wb")
    tmp.write(archivo.getvalue())
    tmp.flush()
    tmp.close()
    return tmp.name


@st.cache_data(show_spinner=False)
def _cargar_instancia_dict(
    csv_path: str, num_vehiculos: int, capacidad: float, soc: float,
    reserva: float, movimientos: int,
) -> dict:
    """Carga la instancia y la devuelve serializada (dict) para poder cachear."""
    inst = load_problem_instance_from_csv(
        csv_path,
        movement_limit=int(movimientos),
        battery_capacity_kwh=float(capacidad),
        reserve_kwh=float(reserva),
        initial_soc=float(soc),
        num_vehicles=int(num_vehiculos),
    )
    return inst.model_dump()


def _resolver(instancia: ProblemInstance, tiempo_limite: float) -> RunResult:
    cfg = SolverConfig(time_limit_seconds=float(tiempo_limite))
    return run(instancia, cfg)


# --------------------------------------------------------------------------- #
# Resolución
# --------------------------------------------------------------------------- #
if resolver:
    # Determinar la ruta del CSV
    if fuente == "Subir CSV":
        if archivo_subido is None:
            st.error("Sube un archivo CSV o cambia a 'Ejemplo del desafío'.")
            st.stop()
        csv_path = _ruta_csv_temporal(archivo_subido)
    else:
        csv_path = os.path.abspath(EJEMPLO_CSV)
        if not os.path.exists(csv_path):
            st.error(f"No se encontró el CSV de ejemplo en:\n{csv_path}")
            st.stop()

    try:
        with st.spinner("Cargando instancia..."):
            inst_dict = _cargar_instancia_dict(
                csv_path, num_vehiculos, capacidad, soc_inicial, reserva, movimientos
            )
            instancia = ProblemInstance.model_validate(inst_dict)
    except Exception as e:  # noqa: BLE001
        st.error(f"Error al cargar la instancia: {e}")
        st.stop()

    # Resumen de la instancia
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nodos", len(instancia.nodes))
    c2.metric("Locales (visitas)", len(instancia.visit_nodes()))
    c3.metric("Cargadores", len(instancia.charger_nodes()))
    c4.metric("Vehículos", instancia.fleet.num_vehicles)

    try:
        with st.spinner("Resolviendo el modelo (esto puede tardar)..."):
            resultado = _resolver(instancia, tiempo_limite)
    except Exception as e:  # noqa: BLE001
        st.error(f"Error al resolver: {e}")
        st.stop()

    st.session_state["resultado"] = resultado.model_dump()
    st.session_state["instancia"] = inst_dict


# --------------------------------------------------------------------------- #
# Resultados (persisten en session_state tras resolver)
# --------------------------------------------------------------------------- #
if "resultado" in st.session_state:
    resultado = RunResult.model_validate(st.session_state["resultado"])
    instancia = ProblemInstance.model_validate(st.session_state["instancia"])

    st.subheader("Resultados")

    k1, k2, k3, k4 = st.columns(4)
    servidas = resultado.served_count if resultado.served_count is not None else len(
        [v for r in resultado.routes for v in r.served_visit_ids]
    )
    k1.metric("Entregas realizadas", servidas)
    k2.metric("Sin atender", len(resultado.unserved_visit_ids))
    energia = resultado.total_energy_kwh
    k3.metric("Energía total (kWh)", f"{energia:.2f}" if energia is not None else "—")
    factible = resultado.validation.feasible if resultado.validation else None
    k4.metric("Factible", "Sí" if factible else "No" if factible is not None else "—")

    tab_mapa, tab_rutas, tab_json = st.tabs(["🗺️ Mapa", "🚗 Rutas", "🧾 JSON"])

    # --- Mapa: dibuja los nodos por tipo ---
    with tab_mapa:
        by_id = instancia.node_by_id()
        filas = []
        for n in instancia.nodes:
            if n.latitude is None or n.longitude is None:
                continue
            color = {
                "base": [0, 128, 255],
                "visit": [0, 180, 0],
                "charger": [255, 140, 0],
            }.get(n.node_type.value, [120, 120, 120])
            filas.append(
                {"lat": n.latitude, "lon": n.longitude, "tipo": n.node_type.value,
                 "color": color, "id": n.node_id}
            )
        if filas:
            df_mapa = pd.DataFrame(filas)
            st.map(df_mapa, latitude="lat", longitude="lon", color="color", size=40)
            st.caption("Azul = depósito · Verde = locales · Naranja = cargadores")
        else:
            st.info("Los nodos no tienen coordenadas para mostrar en el mapa.")

    # --- Rutas: una tabla por vehículo ---
    with tab_rutas:
        if not resultado.routes:
            st.info("No se generaron rutas.")
        for r in resultado.routes:
            st.markdown(f"**Vehículo {r.vehicle_index}** — entregas: {len(r.served_visit_ids)}")
            pasos = [
                {
                    "orden": s.position,
                    "nodo": s.node_id,
                    "energía llegada (kWh)": round(s.arrival_energy_kwh, 3) if s.arrival_energy_kwh is not None else None,
                    "recarga (kWh)": round(s.charge_kwh, 3),
                    "entregas": ", ".join(s.delivered_visit_ids),
                }
                for s in r.steps
            ]
            if pasos:
                st.dataframe(pd.DataFrame(pasos), use_container_width=True, hide_index=True)

    # --- JSON: resultado completo + descarga ---
    with tab_json:
        payload = resultado.model_dump()
        st.download_button(
            "⬇ Descargar resultado (JSON)",
            data=json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            file_name="resultado_ruteo.json",
            mime="application/json",
        )
        st.json(payload)

    # --- Explicación opcional con Bedrock ---
    st.divider()
    st.subheader("Explicación con IA (opcional)")
    st.caption(
        "Usa Amazon Bedrock para resumir el resultado en lenguaje natural. "
        "Requiere credenciales activas (AWS_PROFILE) y un modelo habilitado."
    )
    modelo = st.text_input("BEDROCK_MODEL_ID", value=os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"))
    if st.button("🤖 Explicar con IA"):
        try:
            from ev_routing.llm.bedrock import BedrockClient

            kpis = {
                "entregas": servidas,
                "sin_atender": len(resultado.unserved_visit_ids),
                "energia_total_kwh": energia,
                "factible": factible,
            }
            prompt = (
                "Eres un asistente de logística. Explica en 3 frases, en español y para "
                "una persona no técnica, este resultado de ruteo de vehículos eléctricos. "
                f"Datos: {json.dumps(kpis, ensure_ascii=False, default=str)}"
            )
            with st.spinner("Consultando a Bedrock..."):
                _configurar_credenciales_aws()
                client = BedrockClient(model_id=modelo)
                resp = client.converse(
                    [{"role": "user", "content": [{"text": prompt}]}], max_tokens=300
                )
                texto = "".join(
                    o.get("text", "")
                    for o in resp.get("output", {}).get("message", {}).get("content", [])
                )
            st.success(texto or "(respuesta vacía)")
        except Exception as e:  # noqa: BLE001
            st.error(f"No se pudo consultar Bedrock: {e}")
else:
    st.info("Configura los parámetros en la barra lateral y pulsa **Resolver**.")
