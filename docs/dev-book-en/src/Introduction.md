# Introduction

> [!CAUTION]
> **Note on the currency and accuracy of this documentation**
>
> I strive to keep this developer documentation as up to date as possible. Since I am simultaneously working on the actual project and maintaining the documentation on my own, it is not always possible to reflect every change immediately.
>
> **Please note the following:**
> 
> - **Marking of outdated chapters:** Chapters that are out of date will be marked where possible. However, even unmarked sections may no longer reflect the current state of the code.
> - **Use of AI:** Some text passages were created with the help of AI. I review them, but cannot guarantee that they are free of errors.
> - **General errors** such as typos, inaccurate descriptions, or outdated code examples can occur – even in manually written and unmarked sections.
> - **Your help counts!** If you notice incorrect or outdated chapters, feel free to report them via a GitHub Issue – this helps improve the documentation for everyone.
>
> Treat this documentation as a helpful guide, but when documentation and source code contradict each other, the source code is always right.

Welcome to the developer documentation for the **Streaming Tool** – a project that connects **TikTok events** with **Minecraft**.

This documentation is aimed at developers who want to understand:

- **How the system works internally**
- **How data flows** (TikTok → Processing → Minecraft)
- **How to extend the project** (write your own plugins, customize features)

---

## Where to Start?

| Profile | Recommended starting point |
|--------|----------------------|
| **Basic Python knowledge** | Start with [Basic Concepts](./ch00-00-Fundamentals-and-Concepts.md), then [Setup](./ch00-01-Setting-Up-Local-Development.md) |
| **Advanced Python knowledge** | [System Overview](./ch01-00-How-the-System-Works-Together.md) → [Python in this project](./ch05-00-Python-in-This-Project.md) |
| **Extend & customize with Python** | Go directly to [Plugin Development](./ch02-00-Create-your-own-plugin.md) or [Custom $ Commands](./ch03-06-Creating-Your-Own-$-Command.md) |
| **Debugging / Troubleshooting** | [Debugging & Troubleshooting](./ch06-00-Debugging-and-Troubleshooting.md) |

> [!NOTE]
> If you have knowledge in programming languages other than Python, you can go directly to
> [Create a Plugin without Python](./create-a-plugin-without-Python.md).
> However, you should still look at some chapters to better understand how the system works.
> This will help you even if you don't know Python.
> I also recommend looking at [Create your own Plugin](./ch02-00-Create-your-own-plugin.md) – even though it is primarily written for Python, there is important information there.

---

## Scope & Focus

The project comprises roughly **3,000–4,000 lines of Python code**. We don't analyze every single line – that would be pointless.

Instead, we focus on:

- **Core architectural components** – How is the system structured?
- **Data flows** – How does data move through the system?
- **Patterns & best practices** – What should you pay attention to?
- **Practical application** – How do I write my own plugin?

**In the code itself**, you will find additional comments that serve as signposts for specific details.

---

## Prerequisites

> [!NOTE]
> This documentation explains how the **Streaming Tool system** works – but not Python basics themselves.
> 
> **You need the following prior knowledge:**
> - **Basic Python programming concepts** (functions, classes, loops)
> - **Command line / terminal** navigation
> - **File system** fundamentals
> 
> **If these concepts are new to you:** Complete a beginner Python course first, e.g. [Python.org Tutorial](https://docs.python.org/3/tutorial/) or [Codecademy Python Course](https://www.codecademy.com/learn/learn-python-3). Since we assume these basics here, we save space for depth rather than repetition.

Additionally, you need:

- **Python 3.12+**
- **Git** (for cloning the repository)
- An **editor or IDE** (VS Code, PyCharm, etc.)

Everything required for setup is explained step by step in [Setting Up Local Development](./ch00-01-Setting-Up-Local-Development.md).

---

## Structure of the Documentation

```
00 FUNDAMENTALS
  ├─ Fundamentals & Concepts (What is this system?)
  └─ Local Development Setup (How do I set this up?)

01 SYSTEM OVERVIEW
  ├─ How the system works together
  ├─ Receiving data from TikTok
  ├─ Processing data
  └─ Sending data to Minecraft

02 PYTHON & EVENTS (Core logic)
  ├─ Python in this project
  ├─ The main.py file
  ├─ TikTok Client & Event Handler
  │  └─ Gift Events, Follow Events, Like Events
  └─ Threading & Queues

03 MINECRAFT INTEGRATION
  ├─ From event to command
  ├─ The actions.mca file
  ├─ Mapping logic
  └─ mcfunction files

04 SYSTEM ARCHITECTURE
  ├─ Modular structure
  ├─ Control Methods (DCS vs. ICS)
  ├─ PLUGIN_REGISTRY
  └─ Integration with streaming software

05 PLUGIN DEVELOPMENT
  ├─ Plugin structure & setup
  ├─ Events & Webhooks
  ├─ Config & data storage
  ├─ GUI with pywebview
  ├─ Inter-plugin communication
  └─ Error handling & best practices

06 ADVANCED
  └─ Debugging & Troubleshooting

APPENDIX
  ├─ Project structure
  ├─ Config details
  ├─ Update process
  └─ Glossary (terms explained)
```

The documentation is **progressively built**: Each chapter builds on the previous ones. **But you can always jump to topics that interest you.**

---

## Recommended reading order

**Option 1: Complete walkthrough (best preparation)**

1. [Basic concepts](./ch00-00-Fundamentals-and-Concepts.md)
2. [Setup](./ch00-01-Setting-Up-Local-Development.md)
3. [System overview](./ch01-00-How-the-System-Works-Together.md)
4. [Event processing](./ch05-00-Python-in-This-Project.md)
5. [Minecraft integration](./ch03-00-Mapping-Events-to-Minecraft.md)
6. [System architecture](./ch04-00-System-Modules-and-Integration.md)
7. [Plugin development](./ch02-00-Create-your-own-plugin.md)

**Option 2: Quick start for experienced users**

1. [Basic concepts](./ch00-00-Fundamentals-and-Concepts.md) (10 minutes)
2. [Plugin development](./ch02-00-Create-your-own-plugin.md)
3. Then: Specific chapters depending on your interest

---

## The appendix

In addition to the main chapters, there is an [Appendix](./attachment.md). The appendix contains:

- **Project structure**: Files & folders in detail
- **Config details**: Understanding & extending the configuration file
- **Update process**: How updates work (for maintainers)
- **Glossary**: All technical terms explained

The appendix is a **reference** – you don't have to read it linearly.

---

## How to best use this documentation

1. **Find your level**: Beginner? Then start with [Basic Concepts & Terms](./ch00-00-Fundamentals-and-Concepts.md).
2. **Read progressively**: Chapters build on each other.
3. **Don't skip too quickly**: If something is unclear, go back to previous chapters.
4. **Use the glossary**: Unfamiliar terms? Check the [Glossary](./glossary.md).
5. **Experiment**: Reading is important, but **writing code yourself is crucial**.

---

## Code examples in this documentation

Where we show code examples, we use this formatting:

```python
# Example Python code
from TikTokLive import TikTokLiveClient

client = TikTokLiveClient(unique_id="my_account")
```

**Info blocks:**

> [!TIP]
> Practical recommendation, trick, or best practice to make your work easier or better.

> [!NOTE]
> Supplementary information or background knowledge. Not critical, but often helpful for a better understanding.

> [!IMPORTANT]
> Mandatory information or hard prerequisite. Must be followed for things to work. Not optional.

> [!WARNING]
> Pay close attention here! May lead to errors, problems, or unexpected behavior, but nothing is permanently damaged.

> [!CAUTION]
> Critical notice! Incorrect use can lead to data loss, system errors, or irreversible damage.

---

## Found an error? Questions?

This documentation is constantly being improved. If you:

- **Find errors** → Open a GitHub Issue
- **Something is unclear** → Ask an AI or other developers
- **Have ideas** → Provide feedback in the repository

---

## Good luck!

You are ready. Let's start:

**→ [Basic Concepts & Terms](./ch00-00-Fundamentals-and-Concepts.md)**

or

**→ [Setting Up Local Development](./ch00-01-Setting-Up-Local-Development.md)**