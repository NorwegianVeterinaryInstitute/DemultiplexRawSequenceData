#example

from setuptools import setup

setup(
    name="your_package",
    version="1.0.0",
    packages=["your_package"],
    package_data={"": ["systemd/*.service", "systemd/*.timer"]},
    data_files=[
        ("/etc/systemd/system", ["systemd/demultiplex.service"])
    ],
    install_requires=[
#Caution: This can cause compatibility issues if a future version of multiqc 
# introduces breaking changes. Use version pinning (multiqc<2.0) if stability is a concern.
        "multiqc"  # Specify minimum version if needed
    ],
)

# Use a systemd/ directory for clarity.
# Use data_files to define the installation location.
# Ensure file permissions are correct (e.g., 644 for unit files).

