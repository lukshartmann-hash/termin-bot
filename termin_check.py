"""
Termin-Check fuer GitHub Actions (laeuft in der Cloud, PC muss nicht an sein).
Prueft EINMAL pro Lauf, ob bei der ADHS-Abklaerung (MVZ Noris-Psychotherapie, Terminland)
freie Termine da sind, und schickt dann eine Push-Nachricht ueber ntfy. Bucht NICHT selbst.
Das ntfy-Thema kommt aus dem GitHub-Secret NTFY_TOPIC.
"""
import os
import sys
import time

import requests
from playwright.sync_api import sync_playwright

START_URL = ("https://www.terminland.de/noris-psychotherapie/online/ADHS_new/"
             "default.aspx?m=39059&ll=NrxOD&dpp=NrxOD&css=1")
KEINE_TERMINE_TEXT = "keine freien Termine"
TOPIC = os.environ.get("NTFY_TOPIC", "").strip()


def push(titel, text, prio="urgent"):
    requests.post(f"https://ntfy.sh/{TOPIC}", data=text.encode("utf-8"),
                  headers={"Title": titel, "Priority": prio, "Click": START_URL,
                           "Tags": "rotating_light"}, timeout=15)


def pruefe():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(locale="de-DE").new_page()
        page.goto(START_URL, wait_until="networkidle", timeout=60_000)
        page.get_by_text("ADHS-Abklärung", exact=False).first.click(timeout=15_000)
        page.get_by_role("button", name="Weiter").first.click(timeout=15_000)
        page.wait_for_load_state("networkidle", timeout=60_000)
        time.sleep(2)
        text = page.inner_text("body")
        browser.close()
    if KEINE_TERMINE_TEXT.lower() in text.lower():
        return "keine"
    if "Terminauswahl" in text:
        return "frei"
    return "unklar"


if __name__ == "__main__":
    if not TOPIC:
        sys.exit("Secret NTFY_TOPIC fehlt.")
    if os.environ.get("TEST_PUSH") == "1":
        push("Termin-Bot Test", "Benachrichtigungen funktionieren.", prio="default")
    status = pruefe()  # Fehler -> Lauf schlaegt fehl -> GitHub schickt dir eine Mail
    print("Status:", status)
    if status == "frei":
        push("TERMIN FREI - jetzt buchen!", "ADHS-Abklaerung Noris-Psychotherapie: Seite zeigt Termine. Tippen zum Oeffnen.")
    elif status == "unklar":
        push("Termin-Bot: bitte pruefen", "Seite sieht anders aus als erwartet - evtl. Termine oder Seite geaendert.", prio="high")
