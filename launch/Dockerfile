# Circuit Pathways: the website, the class-code and Pi Link server, and the
# Arduino compilers, in one image. Build it from this folder:
#   docker build -t circuitpathways .   &&   docker run -p 8080:8080 -e CLASS_SECRET=... -e TEACHER_CODES=... circuitpathways

FROM golang:1.24-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
ARG VERSION=dev
RUN CGO_ENABLED=0 go build -trimpath -ldflags "-s -w -X main.Version=${VERSION}" -o /out/launch ./cmd/launch

FROM debian:bookworm-slim
# python3: the ESP8266 compiler's tools use it. No other tools are needed.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app \
    && mkdir /opt/circuitpathways && chown app /opt/circuitpathways
COPY --from=build /out/launch /usr/local/bin/launch
USER app
ENV TOOLS_DIR=/opt/circuitpathways PORT=8080
# Install the pinned compilers, cores and libraries, then compile once for every
# board so the first student's upload isn't slow. This is the slow step (it
# downloads about 1.5 GB), and it is cached until the pinned versions change.
RUN launch -setup -warm
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD ["python3", "-c", "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/healthz'%os.environ.get('PORT','8080'))"]
CMD ["launch"]
