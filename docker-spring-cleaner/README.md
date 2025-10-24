# Docker Spring Cleaner

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg) [![License](https://img.shields.io/badge/license-MIT-green)](../LICENSE)


A production-grade Python script to safely identify and clean up unused Docker resources, including:
- Dangling images (`<none>:<none>`)
- Stopped containers
- Unused volumes
- Unused networks (excluding default `bridge`, `host`, `none` networks)

The script provides a beautiful console output using [Rich](https://github.com/Textualize/rich) tables and prompts for user approval before deletion.

---

## Features

- Lists all dangling images, stopped containers, unused volumes, and unused networks
- Displays tables with clear headers for each resource type
- Prompts **once** for deletion confirmation
- Safe: will **never delete images that are in use** or default networks

---

## Prerequisites

- Python 3.8+
- [Docker](https://www.docker.com/get-started) installed and running
- Python packages:
  ```bash
  pip3 install rich
  ```

---

## Usage
- Clone the repository or download the script:
  ```bash
  git clone https://github.com/yourusername/docker-spring-cleaner.git
  cd docker-spring-cleaner
  ```
- Run the script:
  ```python3
  python3 docker_spring_cleaner.py
  ```
- The script will display all unused resources in separate tables:
   - Dangling Images
   - Stopped Containers
   - Unused Volumes
   - Unused Networks
- You will be prompted to confirm deletion:
  ```bash
  Do you want to delete ALL the above resources? (yes/no):
  ```
- Typing `yes` will safely remove all listed resources.


## Sample Output
```
Dangling Docker Images (<none>:<none>)
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┓
┃ ID           ┃ Name            ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━┩
│ 4fae0a2b1c   │ <none>:<none>   │
└──────────────┴─────────────────┘

Stopped Docker Containers
┏━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ ID         ┃ Name      ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ a1b2c3d4e5 │ my_app    │
└────────────┴───────────┘

Unused Docker Volumes
┏━━━━━━━━━━┓
┃ Name     ┃
┡━━━━━━━━━━┩
│ my_data  │
└──────────┘

Unused Docker Networks
┏━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ ID         ┃ Name      ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ 7c9d8e6f1a │ my_network│
└────────────┴───────────┘
```
