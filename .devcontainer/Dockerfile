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

# Verilator 5.x from source. Ubuntu 22.04 apt is 4.038.
# Do not apt-install verilator, and do not set VERILATOR_ROOT.
ARG VERILATOR_VERSION=5.036
RUN apt-get update && apt-get install -y --no-install-recommends \
        git help2man perl perl-doc python3 make autoconf g++ flex bison \
        libfl2 libfl-dev zlib1g zlib1g-dev \
 && curl -fsSL -o /tmp/verilator.tar.gz \
      "https://github.com/verilator/verilator/archive/refs/tags/v${VERILATOR_VERSION}.tar.gz" \
 && tar -xzf /tmp/verilator.tar.gz -C /tmp \
 && cd /tmp/verilator-${VERILATOR_VERSION} \
 && autoconf \
 && ./configure --prefix=/usr/local \
 && make -j2 \
 && make install \
 && cd / \
 && rm -rf /tmp/verilator.tar.gz /tmp/verilator-${VERILATOR_VERSION} \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

