# Přístupný vzdálený ovladač Androidu

Projekt přístupné Windows aplikace pro kompletní ovládání Android telefonu
klávesnicí, bez nutnosti sledovat displej. Aktuální stav: **Etapa 1 – ADB jádro
(read-only)**.

## Co umí tato verze

- Detekce připojeného zařízení přes ADB (`adb devices -l`).
- Čtení identifikace telefonu (model, Android, HyperOS, build, ABI).
- Čtení stavu přístupnosti (TalkBack, Select to Speak, Reading mode,
  povolené / připojené / havarované služby).
- Bezpečnostní whitelist: příkazy, které mění stav telefonu, jsou odmítnuty
  **dřív**, než se cokoliv spustí (`ovladac/safety.py`).

Neumí ještě: GUI, ovládání prvků, změny nastavení – to jsou další etapy.

## Požadavky

- Windows 11, Python 3.13 (stačí čistý Python, žádné závislosti se neinstalují).
- Android Platform Tools (`adb` v PATH) – ověř příkazem `adb version`.
- Zapnuté USB ladění v telefonu a potvrzený RSA dialog při prvním připojení.

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
