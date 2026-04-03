## Imports

Before we start TikTok processing, we need to understand **which parts of the project** we use and where.

```python
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, FollowEvent, ConnectEvent, LikeEvent
```

---

### What Does That Mean?

In Python:

* `from ... import ...`
  → "Get certain things from a library"

A **library** is simply a collection of pre-written code that we can use instead of writing everything ourselves.

More about it here:
[https://en.wikipedia.org/wiki/Library_(computing)](https://en.wikipedia.org/wiki/Library_%28computing%29)

---

### Why Do We Only Import Certain Parts?

You usually do **not import the complete library**, but only the parts that you actually need. This has several advantages:

* The code remains clearer
* Less unnecessary code is loaded
* It is easier to see what is used in the project

In our case we import:

* `TikTokLiveClient` → establishes the connection to TikTok
* `GiftEvent` → is triggered when a gift is sent
* `FollowEvent` → is triggered when someone follows
* `ConnectEvent` → is triggered when the connection is established
* `LikeEvent` → is triggered when likes are received

The names are relatively self-explanatory and help you quickly understand what they are responsible for.

---

> [!IMPORTANT]
> Before you can use an external library (i.e. one that **does not come standard with Python**), you have to install it.

For this project you will use:

```bash
pip install TikTokLive
```

If that doesn't work, you can alternatively use:

```bash
python -m pip install TikTokLive
```
