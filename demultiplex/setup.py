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
        "multiqc",  # Specify minimum version if needed
        "watchdog", # use watchdog (which uses inotify) to watch for files being created
    ],
)

# inotify has performance issues with large directories, but "large" here means hundreds of
# thousands of files or directories, or a watchlist exceeding the default system limit
# (fs.inotify.max_user_watches, typically 8,192–128,000). Beyond this, performance degrades.

# 201218_M06578_0041_000000000-JF7TM/ has 143,723 files and directories. That should work
# with inotify but we might need to increase fs.inotify.max_user_watches:
# 
# sudo sysctl -w fs.inotify.max_user_watches=524288
# do make this permament 
# echo "fs.inotify.max_user_watches=524288" | sudo tee -a /etc/sysctl.conf


# Use a systemd/ directory for clarity.
# Use data_files to define the installation location.
# Ensure file permissions are correct (e.g., 644 for unit files).

