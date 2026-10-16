"""Adaptador Lambda para la Lambda unificada de ZMD Mobility.

Mangum traduce eventos de API Gateway (HTTP API) al protocolo ASGI de FastAPI.
Handler para la Lambda: `lambda_handler.handler`.
"""
from mangum import Mangum

from app import app

handler = Mangum(app, lifespan="off")
