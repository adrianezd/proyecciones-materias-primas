"""
Generador de esta pagina: el S&P 500 y otros grandes indices y fondos.

    python -m fuente.construir
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import calculo, datos
from .enlaces import HUB, MENU

AQUI = Path(__file__).parent
PROYECTO = AQUI.parent
SALIDA = PROYECTO / "docs"

BASE_URL = "https://adrianezd.github.io/proyecciones-materias-primas"

entorno = Environment(
    loader=FileSystemLoader(AQUI / "plantillas"),
    autoescape=select_autoescape(["html"]),
)

HOY = dt.date.today().isoformat()


def json_seguro(obj) -> str:
    texto = json.dumps(obj, ensure_ascii=False)
    return (texto
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
            .replace(" ", "\\u2028")
            .replace(" ", "\\u2029"))


def escribir(plantilla: str, **contexto) -> None:
    destino = SALIDA / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)

    contexto.setdefault("raiz", "./")
    contexto.setdefault("menu", MENU)
    contexto.setdefault("hub", HUB)
    contexto.setdefault("base_url", BASE_URL)
    contexto.setdefault("ruta", "")
    contexto.setdefault("generado", HOY)

    destino.write_text(entorno.get_template(plantilla).render(**contexto), encoding="utf-8")
    print("  escrito     index.html")


RECIENTE_PUNTOS = 450  # cubre ~2 años a resolucion diaria sin diezmar


def _paquete_activo(nombre: str, unidad: str, serie: list[dict]) -> dict:
    """Resume una serie diaria: ultimo, maximo, caida, volatilidad, anual.

    El tramo reciente se deja a resolucion completa (para que el filtro de
    "ultimo mes" tenga puntos de verdad que dibujar) y solo se reduce el
    tramo antiguo, que se ve igual de bien con menos puntos.
    """
    valores = [p["v"] for p in serie]

    reciente = serie[-RECIENTE_PUNTOS:]
    resto = serie[:-RECIENTE_PUNTOS] if len(serie) > RECIENTE_PUNTOS else []
    paso = max(1, len(resto) // 200)
    serie_grafica = resto[::paso] + reciente

    hace_un_ano = valores[-min(len(valores), 252)]
    anual: dict[int, list[float]] = {}
    for p in serie:
        anual.setdefault(int(p["f"][:4]), []).append(p["v"])

    return {
        "nombre": nombre,
        "unidad": unidad,
        "ultimo": round(valores[-1], 4),
        "maximo": round(max(valores), 4),
        "cambio_ano": round((valores[-1] / hace_un_ano - 1) * 100, 2) if hace_un_ano else 0,
        "peor_caida": calculo.caidas(valores)["peor"],
        "volatilidad": calculo.volatilidad(valores[-365:]),
        "log": max(valores) / max(min(valores), 1e-9) > 50,
        "serie": serie_grafica,
        "anual": [{"anio": a, "rendimiento": round((v[-1] / v[0] - 1) * 100, 1)}
                  for a, v in sorted(anual.items()) if len(v) > 1 and v[0] > 0],
    }


def main() -> None:
    print("Construyendo: materias primas\n")

    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    SALIDA.mkdir(parents=True)
    shutil.copytree(PROYECTO / "estatico", SALIDA / "estatico")

    activos, familias = {}, {}
    for clave, sim_yahoo, sim_stooq, nombre, unidad, familia in datos.ACTIVOS:
        serie = datos.cotizacion(clave, sim_yahoo, sim_stooq)
        if len(serie) < 100:
            continue
        activos[clave] = _paquete_activo(nombre, unidad, serie)
        familias.setdefault(familia, []).append({"clave": clave, "nombre": nombre})

    if not activos:
        print("  SALTADA     materias primas (ningun proveedor de cotizaciones respondio)")
        (SALIDA / ".nojekyll").write_text("", encoding="utf-8")
        return

    lista_fam = list(familias.items())

    escribir(
        "activos.html",
        acento="materias-primas",
        titulo="Oro, plata, petroleo y gas: cotizacion y grafica interactiva",
        descripcion="Historico de cierre diario del oro, la plata, el petroleo Brent y el "
                    "gas natural, con graficas interactivas.",
        encabezado="Materias primas",
        bajada="Oro, plata, petroleo Brent y gas natural. Cierre diario, historico completo.",
        explicacion="Las cotizaciones salen del endpoint de graficas de Yahoo Finance, que "
                    "da historico largo sin pedir clave. Si Yahoo falla, se prueba Stooq, "
                    "que desde marzo de 2026 exige clave propia.",
        fuente_texto="Cotizaciones: Yahoo Finance.",
        familias=lista_fam,
        datos_json=json_seguro({"activos": activos, "primero": lista_fam[0][1][0]["clave"]}),
    )

    (SALIDA / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8"
    )
    (SALIDA / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f'\n  <url><loc>{BASE_URL}/</loc><lastmod>{HOY}</lastmod></url>\n</urlset>\n',
        encoding="utf-8",
    )
    (SALIDA / ".nojekyll").write_text("", encoding="utf-8")

    print("\nListo.")


if __name__ == "__main__":
    main()
