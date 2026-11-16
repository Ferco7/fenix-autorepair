# Evidencia F14: Notificación real y manejo de fallos (Rol I4)

**Fecha:** 2026-11-16
**Responsable:** Alegre, Facundo Sebastián (I4)
**Módulo:** `src/fenix/services/notifications.py`

## 1. Comando ejecutado para el envío real
```bash
python -c "from fenix.services.notifications import notify; notify('Prueba Fénix I4 - Facundo Alegre')"

## 2. Salida real en la terminal
El comando finalizó sin arrojar errores (código de salida 0). La función `notify()` no imprime nada por consola para no dejar rastro de datos sensibles. La confirmación del éxito se verifica con la llegada del mensaje al chat de Telegram (ver evidencia visual abajo).