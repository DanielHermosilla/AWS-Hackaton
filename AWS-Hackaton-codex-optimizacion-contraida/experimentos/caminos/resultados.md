## Tiempos de resolución de caminos (s), por N nodos clave

| N | multi_destino | bidireccional | a_estrella | alt | scipy | networkx |
|---|---|---|---|---|---|---|
| 21 | 0.256 | 1.708 | 1.169 | 2.022 | 0.070 | 1.557 |
| 41 | 0.535 | 5.972 | 5.434 | 7.962 | 0.133 | 3.231 |
| 81 | 1.186 | 28.191 | 15.931 | 24.050 | 0.322 | 6.728 |
| 121 | 2.352 | 57.828 | 47.707 | 60.169 | 0.724 | 11.043 |
| 181 | 3.856 | 154.202 | 63.039 | 84.851 | 0.707 | 10.041 |

## Tiempos de las etapas base (s), por N

| N | carga_grafo | ajuste_calle | adyacencia |
|---|---|---|---|
| 21 | 4.339 | 0.951 | 0.039 |
| 41 | 2.248 | 1.360 | 0.052 |
| 81 | 2.310 | 2.155 | 0.039 |
| 121 | 2.255 | 3.165 | 0.055 |
| 181 | 2.851 | 4.070 | 0.052 |

## Verificación de equivalencia (vs multi_destino)

| N | max_err_rel energía | pares con energía distinta |
|---|---|---|
| 21 | 0.00e+00 | 0 |
| 41 | 0.00e+00 | 0 |
| 81 | 0.00e+00 | 0 |
| 121 | 0.00e+00 | 0 |
| 181 | 0.00e+00 | 0 |
