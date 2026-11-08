# Přístupný vzdálený ovladač Androidu

Projekt přístupné Windows aplikace pro kompletní ovládání Android telefonu
klávesnicí, bez nutnosti sledovat displej. Aktuální stav: **Etapa 2A –
diagnostické GUI (PyQt6, read-only) + ADB jádro (Etapa 1)**.

## Co umí tato verze

- **Diagnostické GUI** (`python main.py`): výběr zařízení, spuštění
  read-only diagnostiky, výsledek ve dvou přístupných tabulkách.
  Vytvořeno výhradně ze standardních widgetů pro čtečku obrazovky (NVDA),
  explicitní pořadí fokusu klávesou Tab, Escape v hlavním okně nic nezavírá.
- Detekce připojeného zařízení přes ADB (`adb devices -l`).
- Čtení identifikace telefonu (model, Android, HyperOS, build, ABI).
- Čtení stavu přístupnosti (TalkBack, Select to Speak, Reading mode,
  povolené / připojené / havarované služby).
- Bezpečnostní whitelist: příkazy, které mění stav telefonu, jsou odmítnuty
  **dřív**, než se cokoliv spustí (`ovladac/safety.py`).

Neumí ještě: ovládání prvků telefonu, změny nastavení – to jsou další etapy
(Etapa 2B a později). GUI je read-only, jako celé jádro.

## Požadavky

- Windows 11, Python 3.13.
- Jádro (CLI) nemá žádné závislosti. GUI navíc vyžaduje PyQt6:
  `pip install .[gui]`.
- Android Platform Tools (`adb` v PATH) – ověř příkazem `adb version`.
- Zapnuté USB ladění v telefonu a potvrzený RSA dialog při prvním připojení.

## Spuštění GUI (Etapa 2A)

```powershell
pip install .[gui]
python main.py
```

Okno se otevře, automaticky načte seznam zařízení a při jediném připojeném
telefonu sám vybere. Tlačítko **Spustit diagnostiku** provede read-only
diagnostiku; výsledek se čte ve tabulkách (řádky se přepínají šipkami
nahoru/dolů, hodnoty ve druhém sloupci). Tlačítko **Obnovit seznam** zopakuje
sken. Zavírá se standardně (Alt+F4); během běhu diagnostiky se zavření
pozastaví, dokud se probíhající (read-only) příkazy dokončí.

### Ruční testovací protokol pro NVDA

Ověření čistě klávesnicí, bez sledování obrazovky:

1. **Otevření:** spusť NVDA, poté `python main.py`. NVDA má oznámit titul
   okna „Přístupný ovladač Androidu – diagnostika“ a současně má focus být
   na combo **Zařízení** (nebo na prvním prvku v pořadí).
2. **Vyjmenování zařízení:** na combo stiskni šipku dolů – NVDA přečte
   každý připojený telefon (serial + stav).
3. **Pořadí fokusu:** Tabem projdi: Zařízení → Obnovit seznam → Spustit
   diagnostiku → tabulka Identifikace → tabulka Služby přístupnosti.
   Pořadí musí být přesně toto, bez přeskakování.
4. **Escape:** stiskni Escape – okno se **nesmí** zavřít (Escape v hlavním
   okně nic nedělá; dialogy by zavřel).
5. **Diagnostika:** na tlačítku Spustit stiskni Enter. Stavová lišta má
   přečíst „Zpracovávám…“. Po dokončení fokus přejde na první řádek tabulky
   Identifikace (pokud čekal na tlačítku).
6. **Řádky tabulek:** šipky nahoru/dolů projdou všechny řádky; každý řádek
   má přístupný popisek (názvový sloupec) i hodnotu (sloupec Stav).
7. **Obnovit:** Tab na tlačítko Obnovit seznam, Enter – sken se opakuje
   a výběr zařízení se obnoví.
8. **Zavření:** Alt+F4. Pokud běží úloha, okno se zavře až po jejím
   dokončení (bez dialogu „zrušeno“ – zrušení není chybou).

## První spuštění diagnostiky

1. Připoj telefon kabelem k PC.
2. V telefonu zkontroluj: Nastavení → O telefonu → Podrobnosti →
   několikrát klepni na „Verze MIUI/HyperOS“ (odemkne možnosti vývojáře),
   pak Nastavení → Další nastavení → Vývojářské možnosti →
   **Ladění USB** zapnuto.
3. Při prvním připojení potvrď na telefonu dialog s otiskem klíče RSA
   („Povolit ladění USB?“) – zaškrtni „Vždy povolit z tohoto počítače“.
4. V PowerShellu z kořene projektu spusť:

   ```powershell
   python scripts\run_diagnostics.py
   ```

5. Skript vypíše identifikaci telefonu, stav přístupnosti a **seznam všech
   příkazů, které skutečně spustil** – měly by být jen čtecí
   (`version`, `devices -l`, `getprop`, `settings get`, `pm list packages`,
   `dumpsys accessibility`).

Očekávaný výstup odpovídá diagnostice z Etapy 0: Xiaomi 13T (2306EPN60G),
Android 16 / HyperOS 3.0.4.0, TalkBack nainstalovaný, ale nepovolený,
Select to Speak povolený a připojený.

## Spuštění testů

```powershell
python -m unittest discover -s tests -t . -v
```

Testy nepotřebují připojený telefon – pracují s reálnými výstupy
z zařízení uloženými v `tests/fixtures/`.

## Struktura projektu

```
pyproject.toml              – metadata projektu (žádné závislosti)
ovladac/
  safety.py                 – whitelist read-only příkazů (jediné místo rozhodování)
  adb.py                    – AdbClient, parsování výstupů, runner s timeoutem
  device_info.py            – identifikace zařízení z getprop
  accessibility.py          – čtení stavu TalkBack / Select to Speak / Reading mode
scripts/
  run_diagnostics.py        – READ-ONLY diagnostický skript
tests/
  test_safety.py            – že zakázané příkazy jsou odmítnuty
  test_adb.py               – parsování, výběr zařízení, timeout, UTF-8
  test_device_info.py       – identifikace zařízení
  test_accessibility.py     – stav přístupnosti + regrese z opravy Etapy 0
  fixtures/                 – reálné výstupy zařízení (Android 16 / HyperOS 3)
```

## Bezpečnostní pravidla (Etapa 1)

Skripty a moduly **nesmějí** spouštět:

- `settings put`, `pm grant`, `pm install`, `pm clear`,
- `input tap/text/keyevent`, `am start`,
- `uiautomator dump` (zapisuje soubor – až po samostatném schválení),
- `adb install`, `adb pair`, `adb forward`, `adb reverse`.

Tyto příkazy jsou odmítnuty ještě před spuštěním procesu
(`SafetyViolationError`). Pro Etapu 2 (schvalovaný `uiautomator dump`) bude
whitelist rozšířen výslovně a odděleně.
