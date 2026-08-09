"""Startet die lokale Wettbewerbs-App.

Aufruf:  python run.py
Danach im Browser öffnen:  http://127.0.0.1:5000
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # host=0.0.0.0 erlaubt Zugriff von Tablet/Handy im selben WLAN.
    # Port 8000, da 5000 unter Windows oft von Docker/WSL belegt ist.
    app.run(host="0.0.0.0", port=8000, debug=True)
