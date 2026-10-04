# VITALS headless ArduCopter SITL + MAVProxy (Apple Silicon / linux/arm64 native)
#
# Scope of this phase: ONE headless ArduCopter SITL instance plus MAVProxy acting as a
# bidirectional MAVLink TCP server on 14550. No Gazebo, no Mission Planner, no GUI,
# no VITALS application code, no database.
#
# Dispatcher/Dispatcher.py:43 connects with:
#   mavutil.mavlink_connection('tcp:127.0.0.1:14550', mavlink_version="2.0")
# i.e. it is a TCP *client*, so MAVProxy must be the TCP *server* (--out tcpin:...).
#
# TWO-STAGE BUILD
# ---------------
#   builder  -> full gcc toolchain, dev headers, git, ArduPilot source + waf tree,
#               and a self-contained MAVProxy virtualenv (so the C extensions it
#               needs -- pymavlink, lxml -- are compiled HERE, never in runtime).
#   runtime  -> fresh Ubuntu, runtime shared libraries only, plus exactly three
#               artifacts copied across: the arducopter binary, the SITL default
#               parameters, and the MAVProxy venv. No compiler, no git, no dev
#               headers, no source checkout, no waf build tree.
#
# SIZE / TIME ESTIMATES (NOT MEASURED -- nothing has been built or pulled yet):
#   base image pull         ~30-80 MB compressed     (estimate)
#   builder stage total     ~3 - 6 GB                (estimate, discarded)
#   final runtime image     ~250 - 600 MB            (estimate)
#   waf copter build        10-30 min                (estimate)
# The builder stage is NOT discarded from the local build cache automatically -- it
# persists until explicitly removed. Measure with `docker system df` after an
# approved build; do not prune anything without approval.
# Replace every number above with a real measurement after an approved build.


# =============================================================================
# Stage 1: builder
# =============================================================================
FROM ubuntu:22.04 AS builder

# Pinned versions. ARDUPILOT_TAG is an upstream git tag.
# NOTE: MAVPROXY_VERSION 1.8.75 is pinned as specified but has NOT been verified
# against PyPI (that would require a network fetch, which is out of scope here).
# If the build fails resolving it, report back rather than floating to latest.
ARG ARDUPILOT_TAG=Copter-4.6.3
ARG MAVPROXY_VERSION=1.8.75

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1

# Compiler/toolchain for ArduPilot waf, plus the dev headers needed to compile
# MAVProxy's C-extension dependencies (pymavlink, lxml) on arm64. Everything here
# stays in this stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        gawk \
        git \
        libtool \
        libxml2-dev \
        libxslt1-dev \
        pkg-config \
        python3 \
        python3-dev \
        python3-pip \
        python3-setuptools \
        python3-venv \
        python3-wheel \
        rsync \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Build MAVProxy into a self-contained virtualenv that the runtime stage copies
# wholesale. This is what keeps gcc and the Python dev headers out of the final
# image: every wheel is built here. The venv lives at the SAME absolute path in
# both stages, so its baked-in paths stay valid.
RUN python3 -m venv /opt/mavproxy-venv \
    && /opt/mavproxy-venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/mavproxy-venv/bin/pip install --no-cache-dir "MAVProxy==${MAVPROXY_VERSION}"

# ArduPilot waf build-time python deps (system interpreter, not the venv).
RUN python3 -m pip install --no-cache-dir \
        "empy==3.3.4" \
        "future" \
        "pexpect"

# Build unprivileged; ArduPilot's waf warns when run as root.
RUN useradd --create-home --shell /bin/bash --uid 1000 sim \
    && mkdir -p /opt/ardupilot \
    && chown -R sim:sim /opt/ardupilot

USER sim
WORKDIR /opt/ardupilot

# Shallow clone of the pinned tag, shallow submodules.
RUN git clone \
        --depth 1 \
        --branch "${ARDUPILOT_TAG}" \
        --recurse-submodules \
        --shallow-submodules \
        https://github.com/ArduPilot/ardupilot.git .

# Native arm64 SITL build -- no QEMU, no cross-compile, no Gazebo plugins.
# Produces build/sitl/bin/arducopter.
RUN ./waf configure --board sitl \
    && ./waf copter


# =============================================================================
# Stage 2: runtime
# =============================================================================
FROM ubuntu:22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1

# Runtime shared libraries ONLY -- no -dev packages, no compiler, no git.
#   libstdc++6 / libgcc-s1 / libatomic1 -> arducopter is dynamically linked against
#       these and they are NOT all present in the minimal ubuntu base image.
#   libxml2 / libxslt1.1                -> runtime .so for lxml (a pymavlink dep),
#       whose compiled extension arrives inside the copied venv.
#   python3                             -> interpreter, stdlib and libpython that
#       the copied venv resolves against (same 3.10 as the builder stage).
#   iproute2                            -> `ss`, used by entrypoint.sh to detect
#       SITL's listener WITHOUT opening a TCP connection (SITL's master port accepts
#       a limited number of clients, so a connect-probe could steal the slot
#       MAVProxy needs).
#   procps                              -> process inspection for supervision.
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash \
        iproute2 \
        libatomic1 \
        libgcc-s1 \
        libstdc++6 \
        libxml2 \
        libxslt1.1 \
        procps \
        python3 \
    && rm -rf /var/lib/apt/lists/*

# Same uid as the builder stage so the copied artifacts keep sensible ownership.
RUN useradd --create-home --shell /bin/bash --uid 1000 sim \
    && mkdir -p /sitl-run /opt/ardupilot/build/sitl/bin /opt/ardupilot/Tools/autotest \
    && chown -R sim:sim /sitl-run /opt/ardupilot

# --- the only three things that cross the stage boundary ---------------------
# 1. MAVProxy, prebuilt venv (identical absolute path as in the builder).
COPY --from=builder --chown=sim:sim /opt/mavproxy-venv /opt/mavproxy-venv

# 2. The compiled SITL binary. Just the binary -- not build/, not the source tree.
COPY --from=builder --chown=sim:sim \
        /opt/ardupilot/build/sitl/bin/arducopter \
        /opt/ardupilot/build/sitl/bin/arducopter

# 3. SITL default parameters. The whole default_params directory, because these
#    files @include one another; copter.parm alone can dangle. Kilobytes in size.
#    Tools/autotest/models/ is deliberately NOT copied: --model quad is a frame
#    built into the binary and needs no external model file. A future switch to a
#    JSON-defined model would require adding that directory.
COPY --from=builder --chown=sim:sim \
        /opt/ardupilot/Tools/autotest/default_params \
        /opt/ardupilot/Tools/autotest/default_params
# ----------------------------------------------------------------------------

# Put the MAVProxy venv first on PATH so `mavproxy.py` resolves without the
# entrypoint needing to know about the venv at all.
ENV PATH="/opt/mavproxy-venv/bin:${PATH}"

ENV ARDUCOPTER_BIN=/opt/ardupilot/build/sitl/bin/arducopter \
    SITL_DEFAULTS=/opt/ardupilot/Tools/autotest/default_params/copter.parm

# Home position matches VITALS mission preset 1 (missionState.py:238, first waypoint).
# Format: lat,lon,alt_m,heading_deg
# The 25 m altitude is a SIMULATION ESTIMATE, not verified local terrain elevation.
# Mission waypoints use relative altitude, so this only shifts reported MSL.
ENV SITL_HOME=28.6013158,-81.2020057,25,0 \
    SITL_MODEL=quad \
    SITL_SPEEDUP=1 \
    SITL_INSTANCE=0 \
    MAVPROXY_TCP_PORT=14550

# Writable scratch for eeprom.bin, SITL logs and MAVProxy state.
WORKDIR /sitl-run

COPY --chown=sim:sim entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER sim

# Container-internal only. Deliberately NOT published to the Mac host:
#   5760 -> raw SITL master link (MAVProxy connects to it inside the container)
# Only 14550 is published, and only on host loopback (see docker-compose.sitl.yml).
EXPOSE 14550

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
