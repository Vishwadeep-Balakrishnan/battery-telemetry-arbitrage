# Telemetry program for docker-compose (mock mode on a laptop).
# Build context is the repo root:  docker build -f telemetry/Dockerfile .
FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake pkg-config libmosquitto-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY CMakeLists.txt .
COPY libina219 libina219
COPY telemetry telemetry
RUN cmake -S . -B build -DBUILD_TESTS=OFF && cmake --build build -j

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends libmosquitto1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/build/telemetry/battery_telemetry /usr/local/bin/
COPY --from=build /src/build/libina219/ina219_read /usr/local/bin/
ENTRYPOINT ["battery_telemetry"]
CMD ["--mock", "--host", "mosquitto"]
