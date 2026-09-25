import json
from pathlib import Path


configuracion = {
    "nombre": "ASTRO",
    "version": "0.1",
    "idiomas": ["es-ES", "en"],
    "limite_mensual_euros": 50,
    "herramientas": {
        "fecha_hora": True,
        "calculadora": True,
    },
}

ruta = Path(__file__).parent / "datos" / "configuracion_astro.json"
ruta.parent.mkdir(exist_ok=True)

with ruta.open("w", encoding="utf-8") as archivo:
    json.dump(configuracion, archivo, ensure_ascii=False, indent=2)

with ruta.open("r", encoding="utf-8") as archivo:
    configuracion_recuperada = json.load(archivo)

assert configuracion_recuperada == configuracion

print(f"Archivo creado: {ruta}")
print(f"Configuración recuperada: {configuracion_recuperada}")
print("Prueba superada: los datos guardados y recuperados coinciden.")
