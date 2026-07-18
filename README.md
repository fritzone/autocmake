# Auto2CMake

Auto2CMake is a pure python utility designed to simplify the process of migrating a project from Autotools or QMake to CMake 2.7 and above! 

By automating the extraction and translation of build configurations, it reduces the manual effort required to modernize project build infrastructures.

## Overview

It is often an incredible undertaking to go from Autotools' `configure.ac` and QMake's `Makefile.am` to a CMake `CMakeLists.txt`. 

This project aims to streamline this process, allowing you to get right back into writing code, instead of worrying about reading hours of documentation.

## Features

* **Build System Translation:** Handles the conversion of Autotools configuration logic into a CMake-compatible syntax.
* **Target Management:** Locates and defines binary build targets (both executables and libraries).
* **Dependency Handling:** Maps external dependencies and compiler flags to CMake's target-based configurations.

## Requirements

* **Python 3.9+**
* This is the only requirement currently!

## Building Auto2CMake

To compile Auto2CMake (`auto2cmake.py`) you can run the following commands:

#### Windows
```bash
    cd path/to/autocmake
    python bundle.py
```

#### Linux/MacOS
```bash
    cd path/to/autocmake
    python3 bundle.py
```


## Usage

Once compiled, Auto2CMake offers two methods of usage.

**Method 1**: Drag and Drop (Easier)
- Originally Auto2CMake was developed to be dropped into the root directory of an Autotools/QMake project, alongside `autotools.ac` or `Makefile.am`.

    #### Windows
    ```bash
    python auto2cmake.py
    ```

    #### Linux/MacOS
    ```bash
    python3 auto2cmake.py
    ```

**Method 2**: Running with Arguments
- If you are dealing with a more complex workflow, or are trying to fully utilize Auto2CMake, then you will likely want to run the script with arguments.
    
    #### Windows
    ```bash
    python auto2cmake.py [OPTIONS]
    ```

    #### Linux/MacOS
    ```bash
    python3 auto2cmake.py [OPTIONS]
    ```

### Options
| Argument | Description |
| :--- | :--- |
| `-h`, `--help` | Displays more detailed information on supported commands. |
| `-d`, `--directory=<dir>` | Sets the working directory (defaults to current directory). |
| `-e`, `--exclude=<dir1:dir2:etc>` | Skips the provided directories during execution. |
| `-c`, `--disable-comments` | Prevents generation of comments in the `CMakeLists.txt` file. |
| `-q`, `--quick` | Enables Quick Mode (ignores Automake/QMake files, scans .cpp for QT). |
| `-r`, `--recursive` | Enables recursive directory walking. |
| `-a`, `--automoc` | Disables CMake Automoc and enables Qt source wrapping. |
| `-v`, `--version=<version>` | Pins the minimum CMake version (defaults to 2.8+). |
