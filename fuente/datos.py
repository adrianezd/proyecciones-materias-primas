"""
Descarga de cotizaciones: oro, plata, petroleo Brent y gas natural.

Stooq exige API key desde marzo de 2026: devuelve una pagina HTML con
instrucciones en vez del CSV. El proveedor por defecto es el endpoint de
graficas de Yahoo Finance, que sigue funcionando sin clave. No es una API
oficial ni documentada, asi que se prueba una cadena de proveedores y se
registra cual ha respondido.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import httpx

CACHE = Path(__file__).parent.parent / "cache"
CACHE.mkdir(exist_ok=True)

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/"
STOOQ = "https://stooq.com/q/d/l/"

CABECERAS_NAVEGADOR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Clave opcional de Stooq:  set STOOQ_APIKEY=...  /  export STOOQ_APIKEY=...
STOOQ_APIKEY = os.environ.get("STOOQ_APIKEY", "").strip()

# (clave, simbolo Yahoo, simbolo Stooq, nombre, unidad, familia)
ACTIVOS = [
    ("oro",    "GC=F", "xauusd", "Oro",            "$/onza",   "Materias primas"),
    ("plata",  "SI=F", "xagusd", "Plata",          "$/onza",   "Materias primas"),
    ("brent",  "BZ=F", "cb.f",   "Petróleo Brent", "$/barril", "Materias primas"),
    ("gas",    "NG=F", "ng.f",   "Gas natural",    "$/MMBtu",  "Materias primas"),
]


def _pide_yahoo(simbolo: str, rango: str) -> list[dict]:
    r = httpx.get(f"{YAHOO}{simbolo}", params={"range": rango, "interval": "1d"},
                  headers=CABECERAS_NAVEGADOR, timeout=40.0, follow_redirects=True)
    r.raise_for_status()
    datos = r.json()

    resultado = (datos.get("chart") or {}).get("result") or []
    if not resultado:
        raise ValueError(f"sin resultado ({(datos.get('chart') or {}).get('error')})")

    bloque = resultado[0]
    marcas = bloque.get("timestamp") or []
    cierres = ((bloque.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []

    filas = []
    for marca, cierre in zip(marcas, cierres):
        if cierre is None:
            continue   # Yahoo mete nulos en los festivos
        filas.append({
            "f": dt.datetime.fromtimestamp(marca, dt.timezone.utc).date().isoformat(),
            "v": round(float(cierre), 6),
        })
    return filas


def _desde_yahoo(simbolo: str) -> list[dict]:
    """Cierres diarios del endpoint de graficas de Yahoo. Sin clave.

    Con range=max, Yahoo no da cierres diarios: comprime todo el historico
    a un punto por trimestre (a veces por mes), asi que un filtro de
    "ultimo mes" no tendria casi nada que dibujar. Se pide ademas range=2y
    con resolucion diaria de verdad, y se cose delante del historico largo
    para que el tramo reciente sí tenga un punto por dia.
    """
    largo = _pide_yahoo(simbolo, "max")
    try:
        reciente = _pide_yahoo(simbolo, "2y")
    except Exception:
        reciente = []

    if not reciente:
        return largo

    corte = reciente[0]["f"]
    return [p for p in largo if p["f"] < corte] + reciente


def _desde_stooq(simbolo: str) -> list[dict]:
    """Solo sirve con clave. Sin ella, Stooq devuelve HTML en vez de CSV."""
    if not STOOQ_APIKEY:
        raise ValueError("Stooq exige apikey desde marzo de 2026 y no hay STOOQ_APIKEY")

    r = httpx.get(STOOQ, params={"s": simbolo, "i": "d", "apikey": STOOQ_APIKEY},
                  headers=CABECERAS_NAVEGADOR, timeout=40.0, follow_redirects=True)
    r.raise_for_status()
    texto = r.text.strip()

    if not texto.lower().startswith("date"):
        raise ValueError(f"no es CSV: {texto[:70]!r}")

    filas = []
    for linea in texto.splitlines()[1:]:
        partes = linea.split(",")
        if len(partes) >= 5:
            try:
                filas.append({"f": partes[0], "v": float(partes[4])})
            except ValueError:
                pass
    return filas


def cotizacion(clave: str, sim_yahoo: str, sim_stooq: str) -> list[dict]:
    """Prueba los proveedores en orden y usa el primero que responda."""
    fichero = CACHE / f"cotiz-{clave}.json"

    intentos = [("yahoo", _desde_yahoo, sim_yahoo), ("stooq", _desde_stooq, sim_stooq)]

    fallos = []
    for nombre, funcion, simbolo in intentos:
        try:
            filas = funcion(simbolo)
            if len(filas) < 50:
                raise ValueError(f"solo {len(filas)} filas")
            fichero.write_text(json.dumps(filas), encoding="utf-8")
            print(f"  {nombre:<10}  {clave} ({len(filas)} dias)")
            return filas
        except Exception as e:
            fallos.append(f"{nombre}: {type(e).__name__}")

    if fichero.exists():
        print(f"  CACHE       {clave}  ({', '.join(fallos)})")
        return json.loads(fichero.read_text(encoding="utf-8"))

    print(f"  FALLO       {clave}  ({', '.join(fallos)})")
    return []
