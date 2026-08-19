"""Build-Kennung der App – wird auf jeder Seite im Fuß angezeigt.

Zweck: sofort sichtbar machen, ob ein Deployment tatsächlich den neuesten
Stand ausliefert (z.B. nach einem Rebuild auf dem NAS). Diese Datei wird bei
jedem für ein Deployment vorbereiteten Stand von Hand hochgezählt – bewusst
kein Auto-Timestamp beim Build, damit der angezeigte Wert eindeutig einem
bekannten Quellcode-Stand entspricht.
"""

BUILD_NUMMER = 60
BUILD_ZEIT = "2026-08-19 21:08"
