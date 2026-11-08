ARG VARIANT=ubuntu-22.04
FROM mcr.microsoft.com/vscode/devcontainers/base:${VARIANT}

ENV DEBIAN_FRONTEND=noninteractive
ENV PDK_ROOT=/home/vscode/ttsetup/pdk
ENV PDK=sky130A

RUN apt update
RUN apt install -y iverilog gtkwave python3 python3-pip python3-venv python3-tk python-is-python3 libcairo2 libpng-dev libqhull-dev

# Clone tt-support-tools
RUN mkdir -p /ttsetup
RUN git clone -b tt10 https://github.com/TinyTapeout/tt-support-tools /ttsetup/tt-support-tools

COPY test/requirements.txt /ttsetup/test_requirements.txt
COPY .devcontainer/copy_tt_support_tools.sh /ttsetup

RUN pip3 install -r /ttsetup/test_requirements.txt -r /ttsetup/tt-support-tools/requirements.txt

# Install verible (for formatting)
RUN umask 022 && \
    curl -L https://github.com/chipsalliance/verible/releases/download/v0.0-3795-gf4d72375/verible-v0.0-3795-gf4d72375-linux-static-x86_64.tar.gz | \
    tar zxf - -C /usr/local --strip-components=1 && \
    chmod 755 /usr/local/bin

# Install openlane
RUN pip3 install openlane==2.1.5

# Verilator 5.x (Ubuntu 22.04 apt is 4.038). Do not set VERILATOR_ROOT.
RUN curl -L -o /tmp/oss-cad-suite.tgz \
      https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2024-11-08/oss-cad-suite-linux-x64-20241108.tgz \
 && tar -xzf /tmp/oss-cad-suite.tgz -C /opt \
 && rm /tmp/oss-cad-suite.tgz \
 && printf '%s\n' \
      'source /opt/oss-cad-suite/environment' \
      'unset VERILATOR_ROOT' \
    > /etc/profile.d/oss-cad-suite.sh \
 && printf '%s\n' \
      'source /opt/oss-cad-suite/environment' \
      'unset VERILATOR_ROOT' \
      'cd /workspaces/TinyTracer' \
    >> /home/vscode/.bashrc

