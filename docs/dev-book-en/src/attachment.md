# Appendix

The appendix is a **reference** for topics that would go too deep in the main chapters or that provide additional context.

Here you will find:

- **Project structure** – Understanding files & folders
- **Configuration** – Config details & migration
- **Update process** – How updates work
- **Glossary** – All technical terms explained (very important!)

---

## What’s in the Appendix?
### [Plugins without Python (main.exe required)](./create-a-plugin-without-Python.md)

How to write plugins in languages other than Python, what you need to keep in mind for registration, and why **main.exe** is mandatory. Also how you can call other files/scripts from main.exe.

[Open chapter](./create-a-plugin-without-Python.md)

---
### [Glossary](./glossary.md) **START HERE if you’re unsure**

This is your **reference**. If you don’t understand a term:

- **Event** – What is that?
- **Queue** – How does a queue work?
- **DCS/ICS** – What is the difference?
- **Threading** – Why is this important?
- And 50+ more terms!

[Open glossary](./glossary.md)

---

### [Core Modules of the Infrastructure](./core-modules.md) 

For **advanced developers**: Understand the technical infrastructure:

- **paths.py** – Path management
- **utils.py** – Load configuration
- **models.py** – Data structures (AppConfig)
- **validator.py** – Syntax validation
- **cli.py** – Command Line Arguments

Here you will learn how the core modules work together and how plugins use them.

[Open core modules](./core-modules.md)

---

### [Project Structure](./project-structure.md)

Understand how the project is organized:

- **src/** – Source code
- **defaults/** – Template configurations
- **config/** – User settings
- **data/** – Persistently stored data
- **build/release/** – Finished distribution

**Important:** Difference between **development structure** and **release structure**.

[Open Project Structure](./project-structure.md)

---

### [Configuration](./config.md)

Details about `config.yaml`:

- How do you load configuration in code?
- What is `config_version`?
- How does config migration work?
- Where do the values go?

[Open Config Details](./config.md)

---

### [Update Process](./update.md)

For maintainers & advanced developers:

- How are updates downloaded?
- What is overwritten and what is not?
- How does the updater update itself?
- Which files are safe?

[Open Update Process](./update.md)

---

## When Should I Use the Appendix?

| Situation | Appendix Chapter |
|-----------|------------------|
| "I don’t understand this term" | → **Glossary** |
| "How does the infrastructure work?" | → **Core Modules** |
| "Where is the config.yaml file?" | → **Project Structure** |
| "What config keys are there?" | → **Configuration** |
| "How do we test updates?" | → **Update Process** |
| "I’m writing a maintainer guide" | → All of the above || "How do I write a plugin without Python?" | → **Plugins without Python** |
---

## The Appendix Is Constantly Being Expanded

If you are missing topics that should be here:

- Database schema
- Performance Optimization Guide
- API documentation
- Migration Guides

...then give feedback or write it yourself! 

---

## See also

- **[Glossary](./glossary.md)** – The most important reference
- **[Debugging & Troubleshooting](./ch06-00-Debugging-and-Troubleshooting.md)** – When something doesn’t work
- **[Main Documentation](./introduction.md)** – Back to the table of contents