## Importe

Bevor wir mit der TikTok-Verarbeitung starten, müssen wir verstehen, **welche Teile des Projekts** wir wo verwenden.

```python
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, FollowEvent, ConnectEvent, LikeEvent
```

---

### Was bedeutet das?

In Python bedeutet:

* `from ... import ...`
  → „Hole bestimmte Dinge aus einer Bibliothek“

Eine **Bibliothek** ist einfach eine Sammlung von vorgefertigtem Code, den wir nutzen können, anstatt alles selbst zu schreiben.

Mehr dazu hier:
[https://en.wikipedia.org/wiki/Library_(computing)](https://en.wikipedia.org/wiki/Library_%28computing%29)

---

### Warum importieren wir nur bestimmte Teile?

Man importiert in der Regel **nicht die komplette Bibliothek**, sondern nur die Teile, die man wirklich braucht. Das hat mehrere Vorteile:

* der Code bleibt übersichtlicher
* es wird weniger unnötiger Code geladen
* es ist klarer, was im Projekt verwendet wird

In unserem Fall importieren wir:

* `TikTokLiveClient` → stellt die Verbindung zu TikTok her
* `GiftEvent` → wird ausgelöst, wenn ein Gift gesendet wird
* `FollowEvent` → wird ausgelöst, wenn jemand folgt
* `ConnectEvent` → wird ausgelöst, wenn die Verbindung hergestellt wird
* `LikeEvent` → wird ausgelöst, wenn Likes eingehen

Die Namen sind relativ selbsterklärend und helfen dabei, schnell zu verstehen, wofür sie zuständig sind.

---

> [!IMPORTANT]
> Bevor du eine externe Bibliothek verwenden kannst (also eine, die **nicht standardmäßig zu Python gehört**), musst du sie installieren.

Für dieses Projekt verwendest du:

```bash
pip install TikTokLive
```

Falls das nicht funktioniert, kannst du alternativ:

```bash
python -m pip install TikTokLive
```

verwenden.