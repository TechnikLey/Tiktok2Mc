# Einführung

Willkommen zur Entwicklerdokumentation von **TikTok2Mc** — einem System, das TikTok-Live-Events mit Minecraft verbindet.

## Für wen ist diese Dokumentation?

Diese Dokumentation richtet sich an Entwickler, die eigene **Plugins** oder **Hooks** für TikTok2Mc erstellen möchten.

- **Plugins** sind eigenständige Programme, die als separate Prozesse laufen und über eine API mit dem Hauptsystem kommunizieren.
- **Hooks** sind leichte, prozessinterne Erweiterungen, die benutzerdefinierte `$`-Befehle für die `actions.mca` bereitstellen.

Du lernst, wie du beide Arten von Erweiterungen erstellst, konfigurierst und in das System integrierst.

## Was diese Dokumentation nicht ist

Diese Dokumentation ist **kein** vollständiges Referenzhandbuch des internen Systems.

Interna, die für die Plugin- und Hook-Entwicklung nicht relevant sind, werden bewusst ausgelassen. Wenn du Implementierungsdetails des Hauptsystems benötigst, lies den Quellcode.

## Wie du diese Dokumentation nutzt

Die Kapitel bauen aufeinander auf. Einsteiger sollten mit [Erste Schritte](./ch01-00-getting-started.md) beginnen und sich Schritt für Schritt vorarbeiten. Erfahrene Entwickler können direkt zur [Plugin-Entwicklung](./ch03-00-plugins.md) oder [Hook-Entwicklung](./ch04-00-hooks.md) springen.

Jedes Hauptkapitel folgt dem gleichen Muster:

1. Konzepte und Hintergrund
2. Schritt-für-Schritt-Anleitung
3. Praktische Beispiele
4. Best Practices

## Voraussetzungen

- **Python 3.12+**
- Grundkenntnisse in Python (Klassen, Funktionen, Module)
- Grundlegende Terminal-/Command-Line-Kenntnisse
- Ein installiertes TikTok2Mc (siehe [Erste Schritte](./ch01-00-getting-started.md))

## Konventionen

In dieser Dokumentation werden folgende Markierungen verwendet:

> [!TIP]
> Praktische Empfehlungen und bewährte Verfahren.

> [!NOTE]
> Hintergrundinformationen und Erläuterungen.

> [!IMPORTANT]
> Wichtige Hinweise, die du beachten musst.

> [!WARNING]
> Potenzielle Fehlerquellen und Fallstricke.

> [!CAUTION]
> Kritische Warnungen vor Datenverlust oder Systemfehlern.

## Code-Beispiele

Code-Beispiele sind in Python geschrieben und folgen dem aktuellen Stand des Systems. Wenn Code und Dokumentation voneinander abweichen, hat der Quellcode Vorrang.
