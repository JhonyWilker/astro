# Ejercicio 1: variables y operaciones
nombre = "Jhony"
horas_activas = 16
horas_descanso = 24 - horas_activas
print(f"1. {nombre} reserva {horas_descanso} horas para descansar.")

# Ejercicio 2: condiciones
temperatura = 24

if temperatura >= 30:
    estado = "hace calor"
elif temperatura >= 20:
    estado = "la temperatura es agradable"
else:
    estado = "hace frío"

print(f"2. Con {temperatura} °C, {estado}.")

# Ejercicio 3: bucle for
tareas = ["revisar el plan", "programar", "probar el resultado"]

print("3. Tareas de hoy:")
for numero, tarea in enumerate(tareas, start=1):
    print(f"   {numero}. {tarea}")

# Ejercicio 4: bucle while
cuenta_atras = 3

print("4. Iniciando ASTRO:")
while cuenta_atras > 0:
    print(f"   {cuenta_atras}...")
    cuenta_atras -= 1

print("   ASTRO listo.")

# Ejercicio 5: función
def evaluar_compra(precio, cantidad, presupuesto):
    total = precio * cantidad

    if total <= presupuesto:
        return f"compra permitida: {total:.2f} €"

    return f"compra rechazada: {total:.2f} € supera el límite"


resultado = evaluar_compra(precio=12.50, cantidad=4, presupuesto=50)
print(f"5. {resultado}.")
