"""Lokale Desktop-App für die Siloplanen-Race-Zeitmessung.

Liest den Arduino Mega 2560 (siehe ../firmware/zeitmessung-mega/) seriell
aus und reicht jede Kontaktauslösung an den bestehenden
/api/zeitmessung/event-Endpoint der Webapp weiter - identisch zum
bisherigen ESP32-Weg, nur über USB statt WLAN. Ereignisse werden erst
lokal in SQLite gepuffert, bevor der Sync versucht wird, damit ein
Netz-/Stromausfall am Veranstaltungsort keine Zeitmessung verliert.
"""
