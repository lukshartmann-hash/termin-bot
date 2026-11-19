"""
Termin-Check fuer GitHub Actions (laeuft in der Cloud, PC muss nicht an sein).
Prueft, ob bei der ADHS-Abklaerung (MVZ Noris-Psychotherapie, Terminland) freie Termine da sind,
und schickt dann eine Push-Nachricht ueber ntfy. Bucht NICHT selbst.

- Geplanter Lauf (stuendlich): prueft LOOP_MINUTES lang alle INTERVALL_MIN Minuten.
- Manueller Lauf: prueft einmal (zum Testen).
- Einzelne Fehlversuche (Seite langsam) werden ignoriert; erst 3 Fehler hintereinander -> Push.
- Taegliches Lebenszeichen: im ersten Lauf, der zwischen 18 und 19 Uhr startet.
Das ntfy-Thema kommt aus dem GitHub-Secret NTFY_TOPIC.
"""
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

START_URL = ("https://www.terminland.de/noris-psychotherapie/online/ADHS_new/"
             "default.aspx?m=39059&ll=NrxOD&dpp=NrxOD&css=1")
KEINE_TERMINE_TEXT = "keine freien termine"
TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
LOOP_MINUTES = int(os.environ.get("LOOP_MINUTES", "0") or 0)
INTERVALL_MIN = 5
FEHLER_BIS_MELDUNG = 3
RUN_URL = os.environ.get("RUN_URL", "")


def log(msg):
    print(f"[{datetime.now(ZoneInfo('Europe/Berlin')):%H:%M:%S}] {msg}", flush=True)


def push(titel, text, prio="urgent", tags="rotating_light"):
    try:
        requests.post(f"https://ntfy.sh/{TOPIC}", data=text.encode("utf-8"),
                      headers={"Title": titel, "Priority": prio, "Click": START_URL, "Tags": tags},
                      timeout=15)
    except Exception as e:
        log(f"Push fehlgeschlagen: {e}")


def body_text(page):
    try:
        return page.inner_text("body", timeout=5_000)
    except Exception:
        return ""


def pruefe(browser):
    ctx = browser.new_context(
        locale="de-DE",
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"))
    page = ctx.new_page()
    try:
        page.goto(START_URL, wait_until="domcontentloaded", timeout=45_000)
        page.get_by_text("ADHS-Abklärung", exact=False).first.wait_for(timeout=30_000)
        page.get_by_text("ADHS-Abklärung", exact=False).first.click(timeout=15_000)
        weiter = page.get_by_role("button", name="Weiter")
        if weiter.count() > 0:
            weiter.first.click(timeout=15_000)
        text = ""
        for _ in range(30):
            text = body_text(page)
            if KEINE_TERMINE_TEXT in text.lower() or "2. Terminauswahl" in text:
                break
            time.sleep(1)
    except Exception:
        log(f"Fehler auf URL: {page.url}")
        log("Seitentext (Anfang):\n" + body_text(page)[:800])
        raise
    finally:
        ctx.close()

    if KEINE_TERMINE_TEXT in text.lower():
        return "keine", text
    if "Terminauswahl" in text and "1. Fragen zum Termin" not in text:
        return "frei", text
    return "unklar", text


def main():
    if not TOPIC:
        sys.exit("Secret NTFY_TOPIC fehlt.")
    if os.environ.get("TEST_PUSH") == "1":
        push("Termin-Bot Test", "Benachrichtigungen funktionieren.", prio="default")
    if LOOP_MINUTES > 0 and datetime.now(ZoneInfo("Europe/Berlin")).hour == 18:
        push("Termin-Bot laeuft", "Taeglicher Check: Bot ist aktiv und prueft weiter.",
             prio="low", tags="white_check_mark")

    ende = time.time() + LOOP_MINUTES * 60
    fehler = 0
    gemeldet = set()
    erfolgreich = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        while True:
            try:
                status, text = pruefe(browser)
                fehler = 0
                erfolgreich += 1
                log(f"Status: {status}")
                if status == "frei" and "frei" not in gemeldet:
                    push("TERMIN FREI - jetzt buchen!",
                         "ADHS-Abklaerung Noris-Psychotherapie: Seite zeigt Termine. Tippen zum Oeffnen.")
                    gemeldet.add("frei")
                elif status == "unklar" and "unklar" not in gemeldet:
                    log("Seitentext (Anfang):\n" + text[:800])
                    push("Termin-Bot: bitte pruefen",
                         "Seite sieht anders aus als erwartet - evtl. Termine oder Seite geaendert.",
                         prio="high")
                    gemeldet.add("unklar")
            except Exception as e:
                fehler += 1
                log(f"Versuch fehlgeschlagen ({fehler}x hintereinander): {str(e)[:200]}")
                if fehler >= FEHLER_BIS_MELDUNG and "fehler" not in gemeldet:
                    push("Termin-Bot hat ein Problem",
                         f"{fehler} Versuche hintereinander fehlgeschlagen. {RUN_URL}",
                         prio="default", tags="warning")
                    gemeldet.add("fehler")

            if time.time() + INTERVALL_MIN * 60 > ende:
                # Bei Einzelpruefung ohne Erfolg: noch 2 Wiederholungen nach 30 s
                if LOOP_MINUTES == 0 and erfolgreich == 0 and fehler < FEHLER_BIS_MELDUNG:
                    time.sleep(30)
                    continue
                break
            time.sleep(INTERVALL_MIN * 60)
        browser.close()

    log(f"Fertig: {erfolgreich} erfolgreiche Pruefungen.")
    if erfolgreich == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
