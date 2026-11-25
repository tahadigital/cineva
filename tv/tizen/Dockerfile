# Mavie Samsung Tizen TV (TU8500 / Tizen 5.5+) Sideloading Container
# Build from repository root:
#   docker build -f tv/tizen/Dockerfile -t mavie-tizen .
# Run (enable Developer Mode 12345 on your Samsung TV first):
#   docker run --rm --network host -e TIZEN_PROFILE=MavieProfile mavie-tizen <TV_IP>

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TIZEN_STUDIO=/opt/tizen-studio \
    PATH="/opt/tizen-studio/tools/ide/bin:/opt/tizen-studio/tools:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip python3 openjdk-11-jre-headless libwebkit2gtk-4.0-37 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY public/vendor/hls.min.js /workspace/public/vendor/hls.min.js
COPY tv /workspace/tv

RUN python3 /workspace/tv/build_tv_packages.py --out-dir /workspace/dist

# Mount your Tizen Studio CLI / certificates into /opt/tizen-studio and /root/tizen-studio-data
# or pass a pre-signed .wgt via volume mount when running against a physical Samsung TV.
ENTRYPOINT ["/bin/bash", "-c", "TV_IP=\"$1\"; if [ -z \"$TV_IP\" ]; then echo 'Kullanim: docker run --rm --network host mavie-tizen <TV_IP>'; exit 1; fi; exec /workspace/tv/tizen/install-tizen.sh \"$TV_IP\" \"${TIZEN_PROFILE:-}\"", "--"]
