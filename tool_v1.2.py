#!/usr/bin/env python3
import os
import subprocess
import sys
import shutil
import time
import logging
from datetime import datetime
from tqdm import tqdm

# Configure logging to file and console.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("template_generator.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# --- Helper Functions ---

def run_command(command):
    """Run a shell command and return stdout as a string."""
    logging.info(f"Running command: {' '.join(command)}")
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        logging.info(f"Command output: {result.stdout.strip()}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running command {' '.join(command)}: {e.stderr}")
        sys.exit(1)

def run_command_with_spinner(command, description="Running command"):
    """Run a command with a spinner/progress bar until completion."""
    logging.info(f"{description}: {' '.join(command)}")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # Create a simple progress bar that updates until process finishes.
    with tqdm(total=100, desc=description, bar_format="{l_bar}{bar}| {elapsed}") as pbar:
        while process.poll() is None:
            pbar.update(1)
            time.sleep(0.1)
        # Ensure the bar finishes.
        pbar.n = 100
        pbar.refresh()
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        logging.error(f"Error: {stderr}")
        raise Exception(stderr)
    logging.info(f"{description} completed.")
    return stdout

def get_installed_packages(package_manager):
    """Return a list of installed packages based on the chosen package manager."""
    packages = []
    if package_manager == "apt":
        output = run_command(["dpkg", "-l"])
        for line in output.splitlines():
            if line.startswith("ii"):
                parts = line.split()
                if len(parts) >= 2:
                    packages.append(parts[1])
    elif package_manager == "yum":
        output = run_command(["yum", "list", "installed"])
        for line in output.splitlines()[1:]:
            parts = line.split()
            if parts:
                pkg = parts[0].split('.')[0]
                packages.append(pkg)
    elif package_manager == "pacman":
        output = run_command(["pacman", "-Q"])
        for line in output.splitlines():
            parts = line.split()
            if parts:
                packages.append(parts[0])
    else:
        logging.error("Unsupported package manager.")
        sys.exit(1)
    return packages

def prompt_operating_system():
    """Prompt the user to choose their operating system from known Linux distributions."""
    print("Select your operating system:")
    print("1: Debian/Ubuntu")
    print("2: CentOS/RHEL/Rocky")
    print("3: Arch Linux")
    choice = input("Enter 1, 2 or 3 [default: 1]: ").strip()
    if choice == "2":
        return "centos"
    elif choice == "3":
        return "arch"
    else:
        return "ubuntu"

def get_package_manager(os_choice):
    """Return the package manager based on the chosen OS."""
    if os_choice in ["debian", "ubuntu"]:
        return "apt"
    elif os_choice == "centos":
        return "yum"
    elif os_choice == "arch":
        return "pacman"
    else:
        return "apt"  # default

def check_tool_installed(tool_command):
    """Check if a given command exists in PATH."""
    exists = shutil.which(tool_command) is not None
    logging.info(f"Checking if {tool_command} is installed: {exists}")
    return exists

def install_provisioning_tool(tool, package_manager):
    """Attempt to install the provisioning tool using the package manager with retries and a spinner."""
    install_commands = {
        "apt": {
            "ansible": ["sudo", "apt-get", "install", "-y", "ansible"],
            "puppet":  ["sudo", "apt-get", "install", "-y", "puppet"]
        },
        "yum": {
            "ansible": ["sudo", "yum", "install", "-y", "ansible"],
            "puppet":  ["sudo", "yum", "install", "-y", "puppet"]
        },
        "pacman": {
            "ansible": ["sudo", "pacman", "-S", "--noconfirm", "ansible"],
            "puppet":  ["sudo", "pacman", "-S", "--noconfirm", "puppet"]
        }
    }
    cmd = install_commands.get(package_manager, {}).get(tool)
    if not cmd:
        logging.error(f"No installation command defined for {tool} with {package_manager}.")
        return False

    choice = input(f"{tool} is not installed. Would you like to install it now? (y/N): ").strip().lower()
    if choice != "y":
        print(f"{tool} will not be installed. Exiting.")
        sys.exit(1)

    max_retries = 3
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            logging.info(f"Attempt {attempt} to install {tool} using {package_manager}.")
            run_command_with_spinner(cmd, description=f"Installing {tool} (attempt {attempt})")
            if check_tool_installed("ansible-playbook" if tool=="ansible" else tool):
                logging.info(f"{tool} installed successfully.")
                return True
        except Exception as e:
            logging.error(f"Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                retry = input("Retry installation? (y/N): ").strip().lower()
                if retry != "y":
                    break
            else:
                print("Max retries reached.")
    print(f"Failed to install {tool}. Exiting.")
    sys.exit(1)

def prompt_provision_method(package_manager):
    """Prompt the user to choose a provisioning method and ensure required tool is installed."""
    print("\nSelect provisioning method:")
    print("1: Shell (install packages via package manager)")
    print("2: Ansible")
    print("3: Puppet")
    choice = input("Enter 1, 2 or 3 [default: 1]: ").strip()
    if choice == "2":
        method = "ansible"
        if not check_tool_installed("ansible-playbook"):
            install_provisioning_tool("ansible", package_manager)
        return method
    elif choice == "3":
        method = "puppet"
        if not check_tool_installed("puppet"):
            install_provisioning_tool("puppet", package_manager)
        return method
    else:
        return "shell"

def generate_install_script(packages, method="shell", package_manager="apt"):
    """Generate the provisioning file based on the chosen method."""
    if method == "shell":
        script_lines = [
            "#!/bin/bash",
            f"sudo {package_manager} update",
            f"sudo {package_manager} install -y " + " ".join(packages)
        ]
        script_content = "\n".join(script_lines)
        filename = "install_packages.sh"
        with open(filename, "w") as f:
            f.write(script_content)
        os.chmod(filename, 0o755)
        logging.info(f"Generated {filename} script.")
    elif method == "ansible":
        playbook = [
            "---",
            "- hosts: all",
            "  become: yes",
            "  vars:",
            "    packages:",
        ]
        for pkg in packages:
            playbook.append(f"      - {pkg}")
        playbook.extend([
            "  tasks:",
            "    - name: Update apt cache",
            "      apt:",
            "        update_cache: yes",
            "    - name: Install packages",
            "      apt:",
            "        name: '{{ packages }}'",
            "        state: present"
        ])
        playbook_content = "\n".join(playbook)
        filename = "playbook.yml"
        with open(filename, "w") as f:
            f.write(playbook_content)
        logging.info(f"Generated {filename} for Ansible provisioning.")
    elif method == "puppet":
        manifest = [
            "# Minimal Puppet manifest",
            "node default {",
            "  package { " + ", ".join([f"'{pkg}'" for pkg in packages]) + ":",
            "    ensure => installed,",
            "  }",
            "}"
        ]
        manifest_content = "\n".join(manifest)
        filename = "manifest.pp"
        with open(filename, "w") as f:
            f.write(manifest_content)
        logging.info(f"Generated {filename} for Puppet provisioning.")

def generate_packer_template(provision_method):
    """Generate a basic Packer HCL template and write it to template.pkr.hcl."""
    # For VirtualBox builder.
    iso_url = "http://releases.ubuntu.com/20.04/ubuntu-20.04.6-live-server-amd64.iso"
    iso_checksum = "<YOUR_ISO_CHECKSUM_HERE>"  # Replace with actual checksum

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    vm_name = f"ubuntu-attackbox-{timestamp}"

    hcl_lines = [
        f'source "virtualbox-iso" "ubuntu_attackbox" {{',
        f'  iso_url           = "{iso_url}"',
        f'  iso_checksum      = "{iso_checksum}"',
        f'  ssh_username      = "packer"',
        f'  ssh_password      = "packer"',
        f'  vm_name           = "{vm_name}"',
        f'  guest_os_type     = "Ubuntu_64"',
        f'  shutdown_command  = "echo \'packer\' | sudo -S shutdown -P now"',
        f'}}',
        "",
        "build {",
        '  sources = [ "source.virtualbox-iso.ubuntu_attackbox" ]',
        ""
    ]
    if provision_method == "shell":
        hcl_lines.extend([
            '  provisioner "shell" {',
            '    script = "install_packages.sh"',
            '  }'
        ])
    elif provision_method == "ansible":
        hcl_lines.extend([
            '  provisioner "ansible-local" {',
            '    playbook_file = "playbook.yml"',
            '  }'
        ])
    elif provision_method == "puppet":
        hcl_lines.extend([
            '  provisioner "shell" {',
            '    inline = ["puppet apply manifest.pp"]',
            '  }'
        ])
    hcl_lines.append("}")
    template_content = "\n".join(hcl_lines)
    with open("template.pkr.hcl", "w") as f:
        f.write(template_content)
    logging.info("Generated Packer template in template.pkr.hcl.")

# --- Main Workflow ---

def main():
    print("=== Packer Template Generator ===")
    logging.info("Starting Packer Template Generator")

    # 1. Ask for the operating system from known options.
    os_choice = prompt_operating_system()
    logging.info(f"Selected OS: {os_choice}")

    # 2. Determine package manager based on OS.
    package_manager = get_package_manager(os_choice)
    logging.info(f"Using package manager: {package_manager}")

    # 3. Scan for installed packages.
    print("\nScanning for installed packages...")
    logging.info("Scanning for installed packages...")
    packages = get_installed_packages(package_manager)
    print(f"Found {len(packages)} installed packages.")
    logging.info(f"Found {len(packages)} installed packages.")

    # 4. Skip system configuration files for now.
    print("\nSkipping system configuration scan...")

    # 5. Ask for the provisioning method.
    provision_method = prompt_provision_method(package_manager)
    logging.info(f"Selected provisioning method: {provision_method}")

    # 6. Generate provisioning file based on chosen method.
    generate_install_script(packages, method=provision_method, package_manager=package_manager)

    # 7. Generate the Packer HCL template.
    generate_packer_template(provision_method)

    # 8. Summary of generated files.
    print("\nGenerated files:")
    print("  - Packer template: template.pkr.hcl")
    if provision_method == "shell":
        print("  - Shell provisioning script: install_packages.sh")
    elif provision_method == "ansible":
        print("  - Ansible playbook: playbook.yml")
    elif provision_method == "puppet":
        print("  - Puppet manifest: manifest.pp")
    
    print("\nYou can now run:")
    print("  packer validate template.pkr.hcl")
    print("  packer build template.pkr.hcl")
    logging.info("Generation complete. Exiting.")

if __name__ == "__main__":
    main()
