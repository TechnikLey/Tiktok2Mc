# Setting Up Local Development

In this chapter you will set up your local development environment. This is a one-time task – then you can start development straight away.

---

## Requirements

### Windows

- **Windows 10 or 11**
- **Python 3.12+** (recommended: Python 3.12)
- **Git** (to clone the repository)
- **PowerShell 7**

### Java & Minecraft Server

- **Java Runtime Environment**: The folder `tools/Java/` must exist (either with Java files or your own Java installation).
- **Minecraft Server**: The file `tools/server.jar` is required (Minecraft server JAR file).

> [!IMPORTANT]
> Make sure both the folder `tools/Java/` and the file `tools/server.jar` are present in your project. Without these, some features (e.g. Minecraft integration) will not work!

### macOS / Linux

- **Python 3.12+** (recommended: Python 3.12)
- **Git**
- **Bash or similar shell**

> [!WARNING]
> The project is mainly developed on **Windows**. Individual features may be restricted on macOS/Linux.
> However, macOS/Linux will be fully supported in future versions.

---

## Step 1: Install Python

### Windows

1. Visit [https://www.python.org/downloads/](https://www.python.org/downloads/)
2. Download the latest **Python 3.X** (Windows x86-64)
3. **Important:** In the installer, enable the option **"Add Python to PATH"**
4. Click "Install Now"

**Check:** Open PowerShell and type:

```powershell
python --version
```

You should see: `Python 3.12.x` (or your version)

### macOS

```bash
brew install python@3.X
```

### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install python3.X python3.X-venv
```

---

## Step 2: Install Git

### Windows

1. Visit [https://git-scm.com/download/win](https://git-scm.com/download/win) or [https://desktop.github.com/download/](https://desktop.github.com/download/)
2. Download the installer
3. Run the installer (default settings are OK)

**Check:**

```powershell
git --version
```

### macOS

```bash
brew install git
```

### Linux

```bash
sudo apt install git
```

---

## Step 3: Clone the Repository

The repository is your local project. You save your work there.

> [!TIP]
> After cloning, check if the folder `tools/Java/` and the file `tools/server.jar` exist. If not, you need to add them yourself (see README or project page for instructions).

There are two options:

### Option 1: Clone with Git (recommended)

```bash
git clone https://github.com/TechnikLey/Streaming_Tool.git
cd Streaming_Tool
```

This takes a few seconds. After that you should have all files locally.

**Advantage:** You can download updates later with `git pull`.

---

### Option 2: Download as a ZIP file

If you don't want to use Git:

1. **Visit the repository:**
   [https://github.com/TechnikLey/Streaming_Tool](https://github.com/TechnikLey/Streaming_Tool)

2. **Click on the green "Code" button** (top right)

3. **Select "Download ZIP"**

4. **Unzip the ZIP file** in a suitable location (e.g. `C:\Users\your_name\Streaming_Tool`)

5. **Open PowerShell and navigate there:**

```powershell
cd C:\Users\your_name\Streaming_Tool
```

**Note:** With the ZIP method you have to manually download updates later (not ideal for development).

---

## Step 4: Create a Python Virtual Environment

A **virtual environment** is like an isolated Python "container" for this project. This prevents conflicts with other Python projects on your system.

> [!NOTE]
> **Virtual environment is optional!**
> 
> If you get started, get errors, or it's too complicated for you: you can also **work directly without venv** (see below).
> We recommend venv for more experienced developers, but it is not mandatory.

---

### Option A: With virtual environment (recommended)

#### Windows

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### macOS / Linux

```bash
python3.12 -m venv venv
source venv/bin/activate
```

> [!NOTE]
> If activation in PowerShell fails, first run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

**Check:** Your shell prompt should change to show `(venv)`:

```
(venv) C:\Streaming_Tool>
```

This means you are in the virtual environment. ✓

**Advantages:**
- ✓ Clean isolation (no conflicts with other projects)
- ✓ Professional development
- ✓ Easy to uninstall (just delete the `venv` folder)

**Disadvantages:**
- ✗ A few extra steps during setup

---

### Option B: Without virtual environment (faster but less clean)

If you want to skip venv, go directly to **Step 5: Install dependencies**.

Then run:

```bash
pip install -r requirements.txt
```

The packages will be installed **globally** on your system.

**Advantages:**
- ✓ Fast setup
- ✓ Less to understand

**Disadvantages:**
- ✗ Packages from different projects may conflict with each other
- ✗ Harder to uninstall/clean up
- ✗ Not ideal for multiple Python projects

---

## Step 5: Install Dependencies

Now let's install all the Python packages the project needs:

> [!NOTE]
> For Minecraft integration, you also need a Java runtime in `tools/Java/` and the file `tools/server.jar`.

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This takes a few minutes. Example output:

```
Collecting TikTokLive==0.8.0
  Using cached ...
Collecting Flask==3.0.0
  Using cached ...
...
Successfully installed TikTokLive-0.8.0 Flask-3.0.0 ...
```

**What will be installed?**

- **TikTokLive**: The API for receiving TikTok events
- **Flask**: A web framework (for webhooks & GUIs)
- **pywebview**: For GUIs (desktop windows)
- **PyYAML**: For config files
- And more...

---

## Step 6: Initialize Configuration

The system needs a `config.yaml` to start.

### If it doesn't exist yet:

```bash
cp defaults/config.default.yaml config/config.yaml
```

This creates a default configuration.

### Basic Settings

Open `config/config.yaml` in your editor (e.g. VS Code) and adjust:

```yaml
# Your TikTok Live account name
tiktok_user: "your_tiktok_name"

# Ports for different modules
MinecraftServerAPI:
  Enable: true
  WebServerPort: 8888
  
Timer:
  Enable: true
  StartTime: 10
  
WinCounter:
  Enable: true
  
DeathCounter:
  Enable: true
```

> [!TIP]
> You don't have to understand everything. The only important thing is:
> 1. `tiktok_user`: Your TikTok channel name
> 2. The ports must not be in use

---

## Step 7: Create First Plugin (Optional)

If you want to quickly create a small test plugin:

```powershell
# Windows
.\create_plugin.ps1

# macOS / Linux
bash create_plugin.ps1
```

The script will ask you for a plugin ID. Enter e.g. `testplugin`.

Afterwards you will find your plugin with boilerplate code under `src/plugins/testplugin/`.

---

## Activating/Deactivating the Virtual Environment

### Next Time (Reactivate Virtual Environment)

**Windows:**
```powershell
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
source venv/bin/activate
```

### When You're Done (Exit Virtual Environment)

```bash
deactivate
```

---

## Common Problems & Solutions

| Problem | Solution |
|---------|----------|
| `python: command not found` | Python not in the PATH. Reinstall and enable "Add Python to PATH". |
| `ModuleNotFoundError: No module named 'TikTokLive'` | `pip install -r requirements.txt` not yet run |
| `Port 8080 already in use` | Another application is using the port. Choose a different port in `config.yaml` |
| `Permission denied` (macOS/Linux) | Run `chmod +x create_plugin.ps1` |
| venv does not activate (PowerShell) | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| `pip: The term 'pip' is not recognized as a name of a cmdlet, function, script file, or executable program.` | Try `python -m pip` instead – this may help |

---

## VS Code Setup (Recommended)

If you use **VS Code** (free, very popular), you can configure it like this:

1. Download VS Code: [https://code.visualstudio.com/](https://code.visualstudio.com/)
2. Open the Streaming_Tool folder: `File → Open Folder`
3. Install these extensions:
   - **Python** (Microsoft)
   - **Pylance** (Microsoft)

4. Set the Python interpreter to your `venv`:
   - `Ctrl+Shift+P` → "Python: Select Interpreter"
   - Choose `./venv/bin/python` (or `.\venv\Scripts\python.exe` on Windows)
   - Alternatively, select Python directly if you don't use a `venv`

That's it! Now you have syntax highlighting, autocomplete, and debugging.

> [!TIP]
> If you encounter problems with any of the steps, check the Internet or YouTube for a solution.

---

## Next Steps

You now have:

✓ Python installed  
✓ The repository cloned  
✓ Dependencies installed  
✓ The config adjusted  
✓ Basic tests completed  

You're ready!

**Next chapter:** [How the system works together](./ch01-00-How-the-System-Works-Together.md)
