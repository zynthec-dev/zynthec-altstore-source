# zynthec-source

Eine schlanke AltStore-/SideStore-Source für eigene IPA-Dateien mit browserbasierter Admin-Seite.

## Enthalten

- `https://source.zynthec.com`: kompatibler AltSource-Feed direkt an der Domainwurzel.
- `https://source.zynthec.com/admin/`: Apps hochladen, entfernen und ihre Metadaten gestalten.
- Automatische Metadaten- und Icon-Erkennung für im Katalog ausgewählte IPA-Dateien.
- GitHub Releases mit eigenem Tag und Änderungstext für jede neue IPA-Version.

Es gibt bewusst keine Installationsseite, keine Loader-Downloads, kein Konfigurationsprofil und keine Zusammenführung fremder Sources.

## Lokal bauen

```bash
python3 scripts/build.py
python3 -m unittest discover -s tests -v
python3 -m http.server 8080 --directory dist
```

Der fertige statische Build liegt in `dist/`.

## Erste IPA

`miPet-0.3-beta.ipa` enthält laut eingebetteter `Info.plist` die Version **0.1.0 (Build 1)**. Diese echten Metadaten werden im Feed verwendet.

IPAs werden nicht in Git eingecheckt. Die vorhandene miPet-Version liegt noch im Release `apps`:

```bash
gh release create apps --title "App downloads" --notes "Binary releases used by zynthec-source."
gh release upload apps miPet-0.3-beta.ipa
```

Neue Versionen erhalten beim Upload aus `/admin/` automatisch einen eigenen Release-Tag und den Text aus „Neu in dieser Version“ als Release Notes. Die Admin-Seite lädt Dateien bis 70 MB über GitHubs Git-Blob-API zwischen; GitHub Actions prüft die IPA, erstellt das Release und aktualisiert den Feed. Die Datei wird nicht in die Git-Historie eingecheckt. Für größere Dateien kann der Workflow **Publish IPA** eine direkte HTTPS-Datei-URL übernehmen und ebenfalls ein neues Release mit Änderungstext erstellen.

## Admin-Zugang

Für `/admin/` wird ein Fine-grained Personal Access Token benötigt, beschränkt auf `zynthec-dev/zynthec-source` mit:

- Repository permission `Contents: Read and write`
- möglichst kurzer Laufzeit

Das Token bleibt in `sessionStorage` des aktuellen Browser-Tabs und wird nur direkt an `api.github.com` übertragen. Es wird nicht in Website, Repository oder Build gespeichert. Die Browser-IPA wird als zunächst unreferenzierter Git-Blob bei GitHub abgelegt; GitHub Actions überführt sie ins Release.

Die App-Verwaltung ermöglicht:

- IPA-Dateien hochzuladen und bei jeder neuen Version ein eigenes GitHub Release mit Änderungstext zu erstellen,
- Namen, Versionstexte, Beschreibungen und Farben zu ändern,
- eigene Icons und Screenshot-URLs zu hinterlegen.

## Deployment

GitHub Actions veröffentlicht vorgemerkte IPAs, lädt ausschließlich im Katalog ausgewählte Release-Dateien, baut und testet die Source bei jedem Push. GitHub Pages stellt das Build-Artefakt bereit; Cloudflare liefert den Feed unter der eigenen Domain aus.

Der aktuelle Live-Stand wird über einen Cloudflare Worker unter `https://source.zynthec.com` ausgeliefert. Die Domainwurzel wird dabei auf das intern erzeugte `source.json` abgebildet.

- Build command bei Cloudflare Pages: `python3 scripts/build.py`
- Output directory: `dist`
- Custom domain: `source.zynthec.com`


## Violette Gestaltung


Das Admin-Panel unterstützt System/Hell/Dunkel, speichert ausschließlich die Darstellungspräferenz in localStorage und bleibt per Tastatur bedienbar. Dezente CSS-Transparenz ist eine Webannäherung; Apples native Liquid-Glass-Materialien werden nur im iOS-Icon verwendet. Reduzierte Bewegung, erhöhter Kontrast und reduzierte Transparenz werden berücksichtigt, soweit der Browser die entsprechenden Medienabfragen unterstützt.

Der isolierte Browsertest `tests/admin-ui.mjs` benötigt Playwright und Chrome. Mit `ADMIN_TEST_URL` lässt sich eine lokale Preview auswählen; `ADMIN_TEST_ROOT` kann alternativ die generierten `dist`-Dateien direkt bereitstellen. `PLAYWRIGHT_MODULE`, `CHROME_PATH` und `ADMIN_SCREENSHOTS` sind optional konfigurierbar. Der Test fängt sämtliche GitHub-Anfragen ab und verwendet ausschließlich Testdaten. Er prüft Reihenfolge, Tastaturbedienung, Abbrechen ohne Schreibzugriff, Theme-Persistenz, mobile Breite und Reduce Motion.

Apps werden alphabetisch aufgeführt. Alte IPA-Dateien im lokalen Projektordner oder in historischen Releases erscheinen nicht erneut, solange sie nicht im Katalog ausgewählt sind.
