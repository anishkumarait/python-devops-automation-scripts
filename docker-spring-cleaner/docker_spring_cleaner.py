import subprocess
from rich.console import Console
from rich.table import Table

console = Console()

# -------------------- Functions --------------------
def get_dangling_images():
    """Return list of dangling images (ID, tag)"""
    result = subprocess.run(
        ["docker", "images", "-f", "dangling=true", "--format", "{{.ID}} {{.Repository}}:{{.Tag}}"],
        capture_output=True, text=True
    )
    images = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        img_id, tag = line.split(" ", 1)
        images.append((img_id, tag))
    return images

def get_stopped_containers():
    """Return list of stopped containers (ID, name)"""
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", "status=exited", "--format", "{{.ID}} {{.Names}}"],
        capture_output=True, text=True
    )
    containers = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        c_id, name = line.split(" ", 1)
        containers.append((c_id, name))
    return containers

def get_unused_volumes():
    """Return list of dangling volumes"""
    result = subprocess.run(
        ["docker", "volume", "ls", "-qf", "dangling=true"],
        capture_output=True, text=True
    )
    return [(v, "") for v in result.stdout.strip().split("\n") if v.strip()]

def get_unused_networks():
    """Return list of unused Docker networks (excluding bridge, host, none)"""
    result = subprocess.run(
        ["docker", "network", "ls", "--format", "{{.ID}} {{.Name}}"],
        capture_output=True, text=True
    )
    networks = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        net_id, name = line.split(" ", 1)
        if name in ["bridge", "host", "none"]:
            continue
        inspect = subprocess.run(
            ["docker", "network", "inspect", "-f", "{{json .Containers}}", name],
            capture_output=True, text=True
        )
        if inspect.stdout.strip() == "{}":
            networks.append((net_id, name))
    return networks

def display_tables(images, containers, volumes, networks):
    """Display all resource tables with separate header line for each"""

    has_items = False

    # Dangling Images
    if images:
        console.print("\n[bold cyan]Dangling Docker Images (<none>:<none>)[/bold cyan]")
        table_img = Table()
        table_img.add_column("ID", style="cyan")
        table_img.add_column("Tag", style="green")
        for img_id, tag in images:
            table_img.add_row(img_id[:12], tag)
        console.print(table_img)
        has_items = True
    else:
        console.print("[green]No dangling images found.[/green]")

    # Stopped Containers
    if containers:
        console.print("\n[bold cyan]Stopped Docker Containers[/bold cyan]")
        table_cont = Table()
        table_cont.add_column("ID", style="cyan")
        table_cont.add_column("Name", style="green")
        for c_id, name in containers:
            table_cont.add_row(c_id[:12], name)
        console.print(table_cont)
        has_items = True
    else:
        console.print("[green]No stopped containers found.[/green]")

    # Unused Volumes
    if volumes:
        console.print("\n[bold cyan]Unused Docker Volumes[/bold cyan]")
        table_vol = Table()
        table_vol.add_column("Name", style="cyan")
        for vol, _ in volumes:
            table_vol.add_row(vol)
        console.print(table_vol)
        has_items = True
    else:
        console.print("[green]No unused volumes found.[/green]")

    # Unused Networks
    if networks:
        console.print("\n[bold cyan]Unused Docker Networks[/bold cyan]")
        table_net = Table()
        table_net.add_column("ID", style="cyan")
        table_net.add_column("Name", style="green")
        for net_id, name in networks:
            table_net.add_row(net_id[:12], name)
        console.print(table_net)
        has_items = True
    else:
        console.print("[green]No unused networks found.[/green]")

    return has_items

def delete_resources(images, containers, volumes, networks):
    """Delete all selected Docker resources"""
    confirm = console.input("\nDo you want to delete ALL the above resources? ([bold red]yes[/bold red]/no): ")
    if confirm.strip().lower() != "yes":
        console.print("[yellow]Aborted by user. No resources deleted.[/yellow]")
        return

    # Delete images
    for img_id, _ in images:
        subprocess.run(["docker", "rmi", "-f", img_id])
        console.print(f"[green]Deleted image {img_id[:12]}[/green]")

    # Delete containers
    for c_id, _ in containers:
        subprocess.run(["docker", "rm", "-f", c_id])
        console.print(f"[green]Deleted container {c_id[:12]}[/green]")

    # Delete volumes
    for vol, _ in volumes:
        subprocess.run(["docker", "volume", "rm", vol])
        console.print(f"[green]Deleted volume {vol}[/green]")

    # Delete networks
    for net_id, name in networks:
        subprocess.run(["docker", "network", "rm", net_id])
        console.print(f"[green]Deleted network {name} ({net_id[:12]})[/green]")

    console.print("[bold green]Cleanup complete![/bold green]")

# -------------------- Main --------------------
if __name__ == "__main__":
    dangling_images = get_dangling_images()
    stopped_containers = get_stopped_containers()
    unused_volumes = get_unused_volumes()
    unused_networks = get_unused_networks()

    has_items = display_tables(dangling_images, stopped_containers, unused_volumes, unused_networks)
    if has_items:
        delete_resources(dangling_images, stopped_containers, unused_volumes, unused_networks)
