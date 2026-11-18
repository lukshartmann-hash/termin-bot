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
KEINE_TERMINE_TEXT = "keine freien termine"
TOPIC = os.environ.get("NTFY_TOPIC", "").strip()


def push(titel, text, prio="urgent"):
    requests.post(f"https://ntfy.sh/{TOPIC}", data=text.encode("utf-8"),
                  headers={"Title": titel, "Priority": prio, "Click": START_URL,
                           "Tags": "rotating_light"}, timeout=15)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def body_text(page):
    try:
        return page.inner_text("body", timeout=5_000)
    except Exception:
        return ""


def pruefe():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale="de-DE",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"))
        page = ctx.new_page()
        try:
            log("Lade Startseite ...")
            page.goto(START_URL, wait_until="domcontentloaded", timeout=45_000)
            log(f"Geladen: {page.url}")

            page.get_by_text("ADHS-Abklärung", exact=False).first.wait_for(timeout=30_000)
            page.get_by_text("ADHS-Abklärung", exact=False).first.click(timeout=15_000)
            log("ADHS-Abklaerung angeklickt")

            weiter = page.get_by_role("button", name="Weiter")
            if weiter.count() > 0:
                weiter.first.click(timeout=15_000)
                log("Weiter angeklickt")
            else:
                log("Kein Weiter-Button gefunden (evtl. direkt weitergeleitet)")

            # bis zu 30 s warten, bis Schritt 2 sichtbar ist
            text = ""
            for _ in range(30):
                text = body_text(page)
                if KEINE_TERMINE_TEXT in text.lower() or "2. Terminauswahl" in text:
                    break
                time.sleep(1)
            log(f"Aktuelle URL: {page.url}")
        except Exception:
            log(f"FEHLER auf URL: {page.url}")
            log("Seitentext (Anfang):\n" + body_text(page)[:1500])
            raise
        finally:
            browser.close()

    if KEINE_TERMINE_TEXT in text.lower():
        return "keine", text
    if "Terminauswahl" in text and "1. Fragen zum Termin" not in text:
        return "frei", text
    return "unklar", text


if __name__ == "__main__":
    if not TOPIC:
        sys.exit("Secret NTFY_TOPIC fehlt.")
    if os.environ.get("TEST_PUSH") == "1":
        push("Termin-Bot Test", "Benachrichtigungen funktionieren.", prio="default")
    status, text = pruefe()  # Fehler -> Lauf schlaegt fehl -> Fehler-Push
    log(f"Status: {status}")
    if status != "keine":
        log("Seitentext (Anfang):\n" + text[:1500])
    if status == "frei":
        push("TERMIN FREI - jetzt buchen!", "ADHS-Abklaerung Noris-Psychotherapie: Seite zeigt Termine. Tippen zum Oeffnen.")
    elif status == "unklar":
        push("Termin-Bot: bitte pruefen", "Seite sieht anders aus als erwartet - evtl. Termine oder Seite geaendert.", prio="high")
