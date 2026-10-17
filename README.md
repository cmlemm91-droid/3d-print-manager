# 🖨️ 3D Print Business Manager

Ein leichtgewichtiges ERP-System für 3D-Druck-Services, optimiert für den Betrieb auf einem Raspberry Pi.

## 🚀 Funktionen
- **Lagerverwaltung:** Materialbestände tracken, Wareneingänge verbuchen und Warnungen bei knappem Bestand.
- **Kundenverwaltung:** Kundenprofile mit vollständigen Adressdaten.
- **Auftragsmanagement:** Druckaufträge mit Zuweisung von Material und Drucker.
- **Professionelle Kalkulation:** Automatische Berechnung von Materialkosten, Maschinenzeit und CAD-Designzeit.
- **Rechnungserstellung:** Generierung von detaillierten PDF-Rechnungen (Einzelaufstellung pro Modell).
- **Dashboard:** Schnelle Übersicht über offene Aufträge und kritische Lagerbestände.

## 🛠️ Installation & Setup

### 1. Voraussetzungen
- Raspberry Pi (empfohlen: Pi 3, 4 oder 5)
- Python 3.10+ installiert

### 2. Installation
```bash
# Projektordner erstellen
mkdir -p ~/print_manager
cd ~/print_manager

# Dateien vom GitHub Repo klonen (oder kopieren)
 git clone https://github.com/cmlemm91-droid/3d-print-manager

# Virtuelle Umgebung erstellen
python3 -m venv .venv
source .venv/bin/activate

# Abhängigkeiten installieren
pip install fastapi uvicorn fpdf2 jinja2 python-multipart

3. Starten

cd ~/print_manager
source .venv/bin/activate
python main.py
Die Anwendung ist dann erreichbar unter: http://<IP-DEINES-PI>:8000

📋 Bedienungsanleitung

1. Lager: Zuerst Materialien anlegen (Preis pro kg angeben).
2. Drucker: Drucker anlegen und deren Kosten pro Stunde definieren.
3. Kunden: Kunden mit Adresse erfassen.
4. Aufträge: Neuen Auftrag anlegen $\rightarrow$ Material und Drucker wählen $\rightarrow$ Gewicht und Zeit eingeben $\rightarrow$ CAD-Zeit hinzufügen.
5. Rechnung: Wenn der Auftrag auf "Fertig" gesetzt wurde, kann über die Kundenübersicht oder die abgeschlossenen Aufträge die PDF-Rechnung generiert werden.

⚠️ Wichtige Hinweise

- Datenbank: Die Datei print_manager.db enthält alle Daten. Bitte regelmäßig Backups dieser Datei erstellen!
- Sicherheit: Die App läuft standardmäßig ohne Passwortschutz im lokalen Netzwerk.
